"""KR integrated alpha portfolio v1 — the pure model (scores, selection, the six fixed architectures, the layer decisions, cash-yield overlay).

EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY. Every Korean date through the development cutoff is outcome-exposed and the three
sealed component studies this integrates (market risk model, industry anatomy, stock within-industry anatomy) were read before it was designed,
so every historical number this study can produce is DEVELOPMENT evidence: architecture comparison only, no prospective validity.

No I/O, no network, no fit, no model, no tuning. Functions receive frames and dictionaries and return tables. The sealed instruments are REUSED,
never copied: within-industry percentiles (`kr_stock_within_industry_anatomy`), industry cohorts and features (`kr_industry_anatomy`), the
market risk candidates (`kr_market_risk_model`) and sizing / execution (`kr_concentrated_portfolio`).

Rules that run through every function and are tested on synthetic data:

* ONE STOCK LAYER, ALWAYS ON. STOCK_SCORE = equal-weight mean of VALUE_SCORE (mean of the within-industry percentiles of bookToMarketProxy and
  earningsYieldProxy, BOTH required) and the within-industry percentile of negativeDownsideVol126. A component that is missing makes the score
  missing; one is never substituted for another. Momentum, liquidity-as-alpha and OCF improvement are not in the score.
* THE INDUSTRY LAYER ONLY RE-ORDERS. INDUSTRY_SCORE = 50% cross-industry percentile of REL_MOM_126 + 50% of BREADTH_ABOVE_MA_126 (both required),
  mapped to every member stock; COMBINED_SCORE = 50% STOCK_SCORE + 50% INDUSTRY_SCORE. Nothing is fitted and nothing is tuned.
* THE MARKET LAYER ONLY SCALES. It never changes eligibility or order: the underlying S or I+S portfolio is built first and the sealed
  Market Risk Model v1 multiplier (1.0 / 0.7 / 0.4) scales the already-selected book. A/B/C share ONE underlying decision and D/E/F share ONE.
* THE SIX PATHS DIFFER ONLY ALONG THE TWO REGISTERED AXES. Same universe, same anchors, same sizing, same costs, same execution code.
* EACH LAYER IS DECIDED ON ITS OWN. There is no grand winner: the final architecture is assembled mechanically from the layer decisions, and a
  genuine return / drawdown trade-off is reported as one, never ranked away.
* CASH YIELD IS A SENSITIVITY. It changes only the return earned by residual cash, as an accounting overlay on the finished primary path.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import kr_concentrated_portfolio as P
from . import kr_factor_anatomy as A
from . import kr_market_risk_model as K
from . import kr_stock_within_industry_anatomy as S

STUDY = "kr-integrated-alpha-portfolio-v1"
SCIENTIFIC_STATUS = "EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY"
DEVELOPMENT_STATEMENT = ("This integrated architecture is built from three sealed, outcome-exposed component studies (market risk model, industry "
                         "anatomy, stock within-industry anatomy) on KR history that is already outcome-exposed. Every historical number it produces is "
                         "DEVELOPMENT evidence for choosing an architecture to record prospectively; it has no prospective validity and validates nothing.")
RETURN_BASIS = A.RETURN_BASIS
BENCHMARK = "069500.KS"
DEVELOPMENT_CUTOFF = "2026-09-14"
FEATURE_START = "2015-01-01"
EVALUATION_START = "2017-01-01"             # first rebalance anchor on or after this date; inherited from the overlay study's firstCoverageDate
STRIDE_KR_SESSIONS = 21
MARKET_REFERENCE = "FDR_KS200"

# ---- the six fixed architectures ------------------------------------------------------------------------------------------------------------------
ARCHITECTURES = {
    "A": {"name": "S", "industry": False, "market": None},
    "B": {"name": "S+M0", "industry": False, "market": "C0"},
    "C": {"name": "S+M1", "industry": False, "market": "C1"},
    "D": {"name": "I+S", "industry": True, "market": None},
    "E": {"name": "I+S+M0", "industry": True, "market": "C0"},
    "F": {"name": "I+S+M1", "industry": True, "market": "C1"},
}
ARCH_ORDER = tuple(ARCHITECTURES)
MARKET_CANDIDATES = ("C0", "C1")
BASES = {"S": {"industry": False, "off": "A", "C0": "B", "C1": "C"}, "I+S": {"industry": True, "off": "D", "C0": "E", "C1": "F"}}
PASSIVE = "PASSIVE_069500"

# ---- stock layer ---------------------------------------------------------------------------------------------------------------------------------
VALUE_COMPONENTS = ("bookToMarketProxy", "earningsYieldProxy")
RISK_COMPONENT = "negativeDownsideVol126"
STOCK_FEATURES = VALUE_COMPONENTS + (RISK_COMPONENT,)
STOCK_WEIGHTS = {"VALUE_SCORE": 0.5, "RISK_SCORE": 0.5}
EXCLUDED_FROM_PRIMARY_SCORE = {"momentum121": "stock momentum is an industry-layer / catalyst question, not part of the stock score",
                               "relative126": "stock momentum is an industry-layer / catalyst question, not part of the stock score",
                               "logAdv60": "liquidity is investability (ADV60 floor), never alpha",
                               "ocfImprovementToAssets": "descriptive only in the sealed anatomy; not a primary score input",
                               "ocfYieldProxy": "not part of the registered VALUE_SCORE", "netIncomeToAssets": "quality family not in the registered score",
                               "ocfToAssets": "quality family not in the registered score", "negativeAccrualsToAssets": "quality family not in the registered score"}
MIN_ELIGIBLE_PER_DATE = 10                  # eligible stocks needed at an anchor to select up to five (twice the book); inherited minimumNamesPerDate
MAX_HOLDINGS = 5

# ---- industry layer ------------------------------------------------------------------------------------------------------------------------------
INDUSTRY_COMPONENTS = ("REL_MOM_126", "BREADTH_ABOVE_MA_126")
INDUSTRY_WEIGHTS = {"REL_MOM_126": 0.5, "BREADTH_ABOVE_MA_126": 0.5}
COMBINED_WEIGHTS = {"STOCK_SCORE": 0.5, "INDUSTRY_SCORE": 0.5}
MIN_INDUSTRIES_RANKED = 5                   # a cross-industry percentile of fewer than five industries is degenerate; the sealed minimum is 6 eligible per date

# ---- portfolio (inherited unchanged from kr-model-overlay-portfolio-v1) --------------------------------------------------------------------------
PORTFOLIO = {"maximumHoldings": MAX_HOLDINGS, "singleNameCap": 0.3, "minimumAdvKrw": 3000000000.0, "minimumDownsideVol": 0.01,
             "maximumAdvFraction": 0.01, "referenceNavKrw": 100000000.0, "buyFixedCost": 0.0015, "sellFixedCost": 0.0045,
             "impactAtOnePercent": 0.0005, "advLookback": 60, "downsideLookback": 126}
COST_STRESS = (1.0, 2.0, 3.0)
CASH_RATE_PRIMARY = "ZERO_KRW_NOMINAL"

# ---- decision bands (inherited from the sealed market risk model's nomination; none invented here) ------------------------------------------------
RETURN_BAND = K.RETURN_BAND                                   # 0.50 pp per year of net annualized return
MEANINGFUL_DRAWDOWN_IMPROVEMENT = K.MEANINGFUL_DRAWDOWN_IMPROVEMENT   # |MDD| at most 90% of the base's
NON_INFERIORITY_DRAWDOWN_BAND = K.NON_INFERIORITY_DRAWDOWN_BAND         # |MDD| at most 110% of the base's
BAND_EPSILON = K.BAND_EPSILON
INTERACTION_DRAWDOWN_RATIO_BAND = 0.10                        # descriptive: the market overlay's |MDD| ratio differs by 10 points with vs without industry

# ---- cash-yield sensitivity (frozen before any portfolio outcome is read) ------------------------------------------------------------------------
CASH_YIELD = {"series": "BOK_POLICY_RATE_PROXY", "path": "data/bok-policy-rates.json",
              "meaning": "Bank of Korea base rate, step function of its dated decision history (event date = first calendar day the rate applies)",
              "lag": "the rate in force on the PREVIOUS session's calendar date applies to the return earned between the previous and this session's close",
              "accrual": "(1 + rate/100) ** (calendar days between the two sessions / 365) - 1, on the primary path's cash weight at the start of the session",
              "variants": ["ZERO", "PROXY", "PROXY_MINUS_HAIRCUT"], "haircutAnnualPp": 0.50, "floor": "ZERO",
              "floorReason": "the source supports no negative investable rate", "changes": "ONLY the return earned by residual cash",
              "neverChanges": ["names", "weights", "market state", "trades", "costs", "layer decisions", "the final architecture"],
              "status": "FROZEN_PROXY_NOT_AN_INVESTABLE_DEPOSIT_OR_BILL_INDEX",
              "notUsed": {"KOFR": "no full-span history is assumed", "ECOS": "an item code is never guessed and the repository's ECOS fetch layer does not exist"}}

FORBIDDEN_OUTPUT_KEY_FRAGMENTS = ("winner", "optimal", "best", "promot", "validated", "verdict", "passfail", "recommend", "productionready")
LAYER_STATUS = {"SUPPORTED": "DEVELOPMENT_SUPPORTED", "NOT_SUPPORTED": "NOT_SUPPORTED", "TRADE_OFF": "PARETO_TRADE_OFF", "BLOCKED": "NOT_EVALUABLE_BLOCKED_PATH"}
INDUSTRY_NOT_SUPPORTED = "INDUSTRY_LAYER_NOT_SUPPORTED"
MARKET_NOT_SUPPORTED = "MARKET_OVERLAY_NOT_SUPPORTED_FOR_FINAL_PORTFOLIO"
NO_UNAMBIGUOUS = "NO_UNAMBIGUOUS_FINAL_ARCHITECTURE"
NO_FINAL_BLOCKED = "NO_FINAL_ARCHITECTURE_BLOCKED_PATH"
PAIR_CLASSES = ("IMPROVES", "NON_INFERIOR_NO_MEANINGFUL_GAIN", "TRADE_OFF", "WORSE", "NOT_EVALUABLE_BLOCKED_PATH")


def assert_no_forbidden_keys(value, path=""):
    if isinstance(value, dict):
        for key, inner in value.items():
            if any(fragment in str(key).lower().replace("_", "") for fragment in FORBIDDEN_OUTPUT_KEY_FRAGMENTS):
                raise ValueError("FORBIDDEN_OUTPUT_KEY: " + path + "/" + str(key))
            assert_no_forbidden_keys(inner, path + "/" + str(key))
    elif isinstance(value, (list, tuple)):
        for inner in value:
            assert_no_forbidden_keys(inner, path)


# =======================================================================================================================================
# Stock layer
# =======================================================================================================================================
def stock_scores(frame):
    """Add the within-industry percentiles, VALUE_SCORE, RISK_SCORE and STOCK_SCORE to the eligible-industry members of ONE signal date.

    `frame` carries date, industry, ticker and the registered features, restricted to members of industries with at least five classified members
    (the sealed within-industry anatomy's eligibility). A percentile needs five finite peer values inside the date x industry; otherwise it is NaN,
    and so is every score that needs it. VALUE_SCORE needs BOTH of its components; STOCK_SCORE needs BOTH VALUE_SCORE and the risk percentile."""
    ranked = S.within_industry_percentiles(frame, columns=STOCK_FEATURES)
    value = ranked[["wi_" + c for c in VALUE_COMPONENTS]].to_numpy(float)
    both = np.isfinite(value).all(axis=1)
    ranked["VALUE_SCORE"] = np.where(both, np.nanmean(np.where(np.isfinite(value), value, 0.0), axis=1), np.nan) if len(value) else np.nan
    ranked["RISK_SCORE"] = ranked["wi_" + RISK_COMPONENT]
    parts = ranked[["VALUE_SCORE", "RISK_SCORE"]].to_numpy(float)
    ok = np.isfinite(parts).all(axis=1)
    ranked["STOCK_SCORE"] = np.where(ok, STOCK_WEIGHTS["VALUE_SCORE"] * parts[:, 0] + STOCK_WEIGHTS["RISK_SCORE"] * parts[:, 1], np.nan)
    return ranked


# =======================================================================================================================================
# Industry layer
# =======================================================================================================================================
def industry_scores(industry_features):
    """{industry: {'INDUSTRY_SCORE', 'relMomPercentile', 'breadthPercentile', 'ranked'}} for ONE signal date.

    `industry_features` maps an eligible industry to the sealed industry-anatomy feature dict. Only industries with BOTH components finite are ranked;
    with fewer than MIN_INDUSTRIES_RANKED of them nothing is scored (a percentile of a handful of industries is not a ranking). Percentiles are the
    sealed average-rank percentile over the industries ranked on THIS date; nothing from another date enters."""
    names = sorted(industry_features)
    values = {c: np.array([industry_features[n].get(c, np.nan) for n in names], float) for c in INDUSTRY_COMPONENTS}
    ok = np.ones(len(names), bool)
    for c in INDUSTRY_COMPONENTS:
        ok &= np.isfinite(values[c])
    out = {n: {"INDUSTRY_SCORE": np.nan, "relMomPercentile": np.nan, "breadthPercentile": np.nan, "ranked": False} for n in names}
    if int(ok.sum()) < MIN_INDUSTRIES_RANKED:
        return out
    pct = {c: A.pct_rank(values[c][ok]) for c in INDUSTRY_COMPONENTS}
    for position, name in enumerate(np.array(names)[ok]):
        rel, breadth = float(pct["REL_MOM_126"][position]), float(pct["BREADTH_ABOVE_MA_126"][position])
        out[str(name)] = {"INDUSTRY_SCORE": INDUSTRY_WEIGHTS["REL_MOM_126"] * rel + INDUSTRY_WEIGHTS["BREADTH_ABOVE_MA_126"] * breadth,
                          "relMomPercentile": rel, "breadthPercentile": breadth, "ranked": True}
    return out


# =======================================================================================================================================
# Eligibility, selection and sizing (the same code serves S and I+S; only the score differs)
# =======================================================================================================================================
def finite(value):
    return value is not None and isinstance(value, (int, float, np.floating, np.integer)) and math.isfinite(value)


def investable(row, cfg=PORTFOLIO):
    """Executable investability facts only; never an alpha statement."""
    return (row.get("tradable") is True and finite(row.get("adv60")) and row["adv60"] >= cfg["minimumAdvKrw"]
            and finite(row.get("downsideVol126")) and row["downsideVol126"] >= cfg["minimumDownsideVol"])


def _flag(value):
    return bool(value) if value is not None and value == value else False


def decision_rows(scored, industry_map):
    """One row per member stock of an eligible industry with STOCK_SCORE, INDUSTRY_SCORE and COMBINED_SCORE. `scored` is the `stock_scores` frame
    plus tradable / adv60 / downsideVol126; `industry_map` is `industry_scores` output. The combined score exists only when both parts do."""
    rows = []
    for record in scored.to_dict("records"):
        industry = industry_map.get(record["industry"], {})
        stock, ind = record.get("STOCK_SCORE"), industry.get("INDUSTRY_SCORE", np.nan)
        combined = (COMBINED_WEIGHTS["STOCK_SCORE"] * stock + COMBINED_WEIGHTS["INDUSTRY_SCORE"] * ind) if finite(stock) and finite(ind) else np.nan
        rows.append({"ticker": record["ticker"], "industry": record["industry"], "STOCK_SCORE": stock, "VALUE_SCORE": record.get("VALUE_SCORE"),
                     "RISK_SCORE": record.get("RISK_SCORE"), "INDUSTRY_SCORE": ind, "COMBINED_SCORE": combined,
                     "tradable": _flag(record.get("tradable")), "adv60": record.get("adv60"), "downsideVol126": record.get("downsideVol126")})
    return rows


def underlying_decision(rows, with_industry, cfg=PORTFOLIO):
    """The underlying (pre-market) portfolio decision of ONE signal date for the S book (`with_industry` False, ordered by STOCK_SCORE) or the I+S
    book (True, ordered by COMBINED_SCORE). Eligible = score finite AND investable. Up to five by (-score, ticker); inverse-downside-volatility
    water-fill sizing with the 30% name cap and the ADV capacity cap; residual stays cash. The market multiplier is NOT an input."""
    key = "COMBINED_SCORE" if with_industry else "STOCK_SCORE"
    seen = [r["ticker"] for r in rows]
    if len(set(seen)) != len(seen):
        raise ValueError("DUPLICATE_SELECTION_SECURITY")
    eligible = [r for r in rows if finite(r.get(key)) and investable(r, cfg)]
    ordered = sorted(eligible, key=lambda r: (-r[key], r["ticker"]))
    chosen = ordered[:cfg["maximumHoldings"]]
    base = P.size(chosen, cfg) if chosen else {}
    kept = ("STOCK_SCORE", "INDUSTRY_SCORE", "COMBINED_SCORE") if with_industry else ("STOCK_SCORE",)       # OFF: the industry appears nowhere in the S book
    return {"layer": "I+S" if with_industry else "S", "scoreUsed": key, "eligibleCount": len(eligible),
            "depthOk": len(eligible) >= MIN_ELIGIBLE_PER_DATE, "selected": [r["ticker"] for r in chosen], "baseWeights": base,
            "scores": {r["ticker"]: {k: (None if not finite(r.get(k)) else float(r[k])) for k in kept} for r in chosen}}


def underlying_pair(rows, cfg=PORTFOLIO):
    """Both underlying decisions of one signal date. The market layer is applied to these AFTER they exist, never to build them."""
    return {"S": underlying_decision(rows, False, cfg), "I+S": underlying_decision(rows, True, cfg)}


def decision_for(architecture, pair):
    """The underlying decision an architecture trades. B and C get A's (the SAME object); E and F get D's."""
    return pair["I+S" if ARCHITECTURES[architecture]["industry"] else "S"]


# =======================================================================================================================================
# Market layer schedule (the sealed model's own targets; this study adds nothing)
# =======================================================================================================================================
def market_schedule(states, sessions, start, end):
    """{candidate: DataFrame(decisionDate, executionDate, target, heldForMissingState)} for C0 and C1 from the sealed model functions."""
    schedule = K.decision_schedule(sessions, start, end)
    out = {}
    for cid in MARKET_CANDIDATES:
        targets = K.candidate_targets(states, schedule, cid)
        out[cid] = schedule.merge(targets, on="decisionDate")
    return out


def target_in_force(table, day):
    """The multiplier of the latest decision whose execution session is on or before `day` (a trade at that close), or None before the first."""
    executions = pd.DatetimeIndex(table["executionDate"])
    position = executions.searchsorted(pd.Timestamp(day), side="right") - 1
    return None if position < 0 else float(table["target"].iloc[position])


# =======================================================================================================================================
# The pairwise band classification and the layer decisions
# =======================================================================================================================================
def classify_pair(candidate, base):
    """candidate / base: {'netAnnualizedReturn', 'maxDrawdown' (negative)}. The sealed market model's bands, applied symmetrically.

    non-inferior   = return >= base - 0.50 pp AND |MDD| <= 1.10 x base's
    meaningful gain = return >= base + 0.50 pp (efficiency) OR |MDD| <= 0.90 x base's (protection)
    IMPROVES = non-inferior with a meaningful gain; NON_INFERIOR_NO_MEANINGFUL_GAIN = non-inferior without one;
    TRADE_OFF = fails non-inferiority on one axis but gains meaningfully on the other (a risk-preference choice this study does not make);
    WORSE = fails non-inferiority and gains nothing."""
    values = [candidate.get("netAnnualizedReturn"), candidate.get("maxDrawdown"), base.get("netAnnualizedReturn"), base.get("maxDrawdown")]
    if any(not finite(v) for v in values):
        return "NOT_EVALUABLE_BLOCKED_PATH"
    rc, dc, rb, db = values
    return_ok = rc >= rb - RETURN_BAND - BAND_EPSILON
    drawdown_ok = abs(dc) <= (1 + NON_INFERIORITY_DRAWDOWN_BAND) * abs(db) + BAND_EPSILON
    efficiency = rc >= rb + RETURN_BAND - BAND_EPSILON
    protection = abs(dc) <= (1 - MEANINGFUL_DRAWDOWN_IMPROVEMENT) * abs(db) + BAND_EPSILON
    if return_ok and drawdown_ok:
        return "IMPROVES" if (efficiency or protection) else "NON_INFERIOR_NO_MEANINGFUL_GAIN"
    if (not return_ok and protection) or (not drawdown_ok and efficiency):
        return "TRADE_OFF"
    return "WORSE"


def axes(summary):
    return {"netAnnualizedReturn": (summary or {}).get("netAnnualizedReturn"), "maxDrawdown": (summary or {}).get("maxDrawdown")}


def pair_class(summaries, candidate, base):
    c, b = summaries.get(candidate) or {}, summaries.get(base) or {}
    if not c.get("complete") or not b.get("complete"):
        return "NOT_EVALUABLE_BLOCKED_PATH"
    return classify_pair(axes(c), axes(b))


def layer_status(primary, contexts):
    """SUPPORTED needs the primary pair to IMPROVE and no context pair to be WORSE; a primary TRADE_OFF is its own outcome; any unevaluable pair
    (a blocked path) makes the layer unevaluable rather than guessing."""
    classes = [primary] + list(contexts)
    if any(c == "NOT_EVALUABLE_BLOCKED_PATH" for c in classes):
        return LAYER_STATUS["BLOCKED"]
    if primary == "TRADE_OFF":
        return LAYER_STATUS["TRADE_OFF"]
    if primary == "IMPROVES" and all(c != "WORSE" for c in contexts):
        return LAYER_STATUS["SUPPORTED"]
    return LAYER_STATUS["NOT_SUPPORTED"]


def industry_decision(summaries):
    """I+S versus S under market OFF (primary) and under C0 / C1 (contexts that must not contradict it)."""
    classes = {"marketOff": pair_class(summaries, "D", "A"), "underC0": pair_class(summaries, "E", "B"), "underC1": pair_class(summaries, "F", "C")}
    status = layer_status(classes["marketOff"], [classes["underC0"], classes["underC1"]])
    name = {LAYER_STATUS["SUPPORTED"]: "INDUSTRY_LAYER_DEVELOPMENT_SUPPORTED", LAYER_STATUS["NOT_SUPPORTED"]: INDUSTRY_NOT_SUPPORTED,
            LAYER_STATUS["TRADE_OFF"]: "INDUSTRY_LAYER_PARETO_TRADE_OFF", LAYER_STATUS["BLOCKED"]: "INDUSTRY_LAYER_NOT_EVALUABLE_BLOCKED_PATH"}[status]
    return {"layerDecision": name, "status": status, "pairClasses": classes}


def market_decisions(summaries):
    """C0 and C1 judged SEPARATELY, on each underlying portfolio (S and I+S): the primary pair is the overlay against the SAME portfolio without it;
    the context pair is the same overlay on the other portfolio. C1 against C0 is recorded beside, never as a promotion."""
    out = {}
    for base, cfg in BASES.items():
        other = "I+S" if base == "S" else "S"
        for cid in MARKET_CANDIDATES:
            primary = pair_class(summaries, BASES[base][cid], BASES[base]["off"])
            context = pair_class(summaries, BASES[other][cid], BASES[other]["off"])
            out.setdefault(base, {})[cid] = {"primaryPair": primary, "contextPairOnOtherPortfolio": context, "status": layer_status(primary, [context])}
        out[base]["C1_vs_C0"] = pair_class(summaries, BASES[base]["C1"], BASES[base]["C0"])
    return out


def final_architecture(industry, market):
    """Assembled mechanically from the layer decisions. No tie-break, no preference, no composite score."""
    if industry["status"] == LAYER_STATUS["BLOCKED"]:
        return {"finalArchitecture": NO_FINAL_BLOCKED, "reason": "INDUSTRY_LAYER_NOT_EVALUABLE"}
    if industry["status"] == LAYER_STATUS["TRADE_OFF"]:
        return {"finalArchitecture": NO_UNAMBIGUOUS, "reason": "INDUSTRY_LAYER_PARETO_TRADE_OFF"}
    base = "I+S" if industry["status"] == LAYER_STATUS["SUPPORTED"] else "S"
    chosen = market[base]
    statuses = {cid: chosen[cid]["status"] for cid in MARKET_CANDIDATES}
    if any(s == LAYER_STATUS["BLOCKED"] for s in statuses.values()):
        return {"finalArchitecture": NO_FINAL_BLOCKED, "reason": "MARKET_LAYER_NOT_EVALUABLE", "underlying": base}
    supported = [cid for cid in MARKET_CANDIDATES if statuses[cid] == LAYER_STATUS["SUPPORTED"]]
    if supported:
        pick = supported[0]
        if len(supported) == 2:
            pick = "C1" if chosen["C1_vs_C0"] == "IMPROVES" else "C0"
        letter = BASES[base][pick]
        return {"finalArchitecture": letter, "name": ARCHITECTURES[letter]["name"], "underlying": base, "marketCandidate": pick,
                "marketLayer": "DEVELOPMENT_SUPPORTED:" + "+".join(supported), "reason": "ASSEMBLED_FROM_LAYER_DECISIONS"}
    if any(s == LAYER_STATUS["TRADE_OFF"] for s in statuses.values()):
        return {"finalArchitecture": NO_UNAMBIGUOUS, "reason": "MARKET_LAYER_PARETO_TRADE_OFF", "underlying": base}
    letter = BASES[base]["off"]
    return {"finalArchitecture": letter, "name": ARCHITECTURES[letter]["name"], "underlying": base, "marketCandidate": None,
            "marketLayer": MARKET_NOT_SUPPORTED, "reason": "ASSEMBLED_FROM_LAYER_DECISIONS"}


def decide(summaries):
    industry = industry_decision(summaries)
    market = market_decisions(summaries)
    return {"industry": industry, "market": market, **final_architecture(industry, market)}


# =======================================================================================================================================
# Comparisons (descriptive; every pair uses the same sessions and anchors)
# =======================================================================================================================================
COMPARISONS = (
    ("INDUSTRY_VALUE", "I+S vs S, market off", "D", "A"), ("INDUSTRY_VALUE", "I+S+M0 vs S+M0", "E", "B"), ("INDUSTRY_VALUE", "I+S+M1 vs S+M1", "F", "C"),
    ("MARKET_VALUE", "S+M0 vs S", "B", "A"), ("MARKET_VALUE", "S+M1 vs S", "C", "A"),
    ("MARKET_VALUE", "I+S+M0 vs I+S", "E", "D"), ("MARKET_VALUE", "I+S+M1 vs I+S", "F", "D"),
    ("C1_VS_C0", "S+M1 vs S+M0", "C", "B"), ("C1_VS_C0", "I+S+M1 vs I+S+M0", "F", "E"))
COMPARED_METRICS = ("netAnnualizedReturn", "excessAnnualizedVsPassive", "maxDrawdown", "worstRollingReturnH63", "worstRollingReturnH126", "annualizedVolatility",
                    "downsideVolatility", "annualizedCostDrag", "annualizedOneWayTurnover", "averageGrossEquityExposure", "averageHoldings", "annualizedReplacements")


def difference(candidate, base):
    out = {}
    for metric in COMPARED_METRICS:
        a, b = candidate.get(metric), base.get(metric)
        out[metric] = float(a - b) if finite(a) and finite(b) else None
    return out


def comparisons(summaries):
    rows = []
    for family, label, candidate, base in COMPARISONS:
        rows.append({"family": family, "comparison": label, "candidate": candidate, "base": base,
                     "bandClass": pair_class(summaries, candidate, base),
                     "difference": difference(summaries.get(candidate) or {}, summaries.get(base) or {}) if
                     (summaries.get(candidate) or {}).get("complete") and (summaries.get(base) or {}).get("complete") else None})
    return rows


def interaction(summaries):
    """Whether the market overlay's value differs with versus without the industry layer. Descriptive only: two differences of differences, no
    interaction model, no test."""
    out = {}
    for cid in MARKET_CANDIDATES:
        s_on, s_off = summaries.get(BASES["S"][cid]) or {}, summaries.get(BASES["S"]["off"]) or {}
        i_on, i_off = summaries.get(BASES["I+S"][cid]) or {}, summaries.get(BASES["I+S"]["off"]) or {}
        if not all(x.get("complete") for x in (s_on, s_off, i_on, i_off)):
            out[cid] = {"status": "NOT_EVALUABLE_BLOCKED_PATH"}
            continue
        value_s = difference(s_on, s_off)
        value_i = difference(i_on, i_off)
        ratio_s, ratio_i = abs(s_on["maxDrawdown"]) / abs(s_off["maxDrawdown"]), abs(i_on["maxDrawdown"]) / abs(i_off["maxDrawdown"])
        d_return = value_i["netAnnualizedReturn"] - value_s["netAnnualizedReturn"]
        out[cid] = {"status": "DESCRIPTIVE", "marketValueWithoutIndustry": value_s, "marketValueWithIndustry": value_i,
                    "returnValueDifference": d_return, "drawdownRatioWithoutIndustry": ratio_s, "drawdownRatioWithIndustry": ratio_i,
                    "drawdownRatioDifference": ratio_i - ratio_s,
                    "returnValueDiffersMaterially": abs(d_return) >= RETURN_BAND - BAND_EPSILON,
                    "drawdownValueDiffersMaterially": abs(ratio_i - ratio_s) >= INTERACTION_DRAWDOWN_RATIO_BAND - BAND_EPSILON}
    return out


def attribution(summaries):
    """Industry ON vs OFF, C0 vs OFF, C1 vs OFF, C1 vs C0: the same pairs, grouped by the question they answer."""
    def group(pairs):
        return [{"candidate": c, "base": b, "bandClass": pair_class(summaries, c, b),
                 "difference": difference(summaries.get(c) or {}, summaries.get(b) or {}) if (summaries.get(c) or {}).get("complete")
                 and (summaries.get(b) or {}).get("complete") else None} for c, b in pairs]
    return {"industryOnVsOff": group([("D", "A"), ("E", "B"), ("F", "C")]), "c0VsOff": group([("B", "A"), ("E", "D")]),
            "c1VsOff": group([("C", "A"), ("F", "D")]), "c1VsC0": group([("C", "B"), ("F", "E")])}


# =======================================================================================================================================
# Cash-yield sensitivity: an accounting overlay on the finished primary path
# =======================================================================================================================================
def policy_rate_in_force(events, calendar_day):
    """The Bank of Korea base rate (percent per year) in force on `calendar_day`: the last event dated on or before it. None before the first event."""
    rate = None
    for event in events:
        if event["date"] <= calendar_day:
            rate = float(event["annualRatePct"])
        else:
            break
    return rate


def cash_variant_rate(rate, variant):
    if variant == "ZERO":
        return 0.0
    if rate is None:
        raise ValueError("CASH_RATE_UNAVAILABLE")
    if variant == "PROXY":
        return max(rate, 0.0)
    if variant == "PROXY_MINUS_HAIRCUT":
        return max(rate - CASH_YIELD["haircutAnnualPp"], 0.0)
    raise ValueError("UNREGISTERED_CASH_VARIANT")


def cash_overlay_nav(records, events, variant):
    """NAV of the primary path with residual cash earning the registered rate. For each session after the first, the return earned is the primary
    path's own daily return PLUS (cash weight at the start of the session x the cash return for the calendar gap since the previous session). The
    primary path's holdings, weights, trades and costs are read, never changed."""
    if variant == "ZERO":
        return [float(r["nav"]) for r in records]
    nav = [float(records[0]["nav"])]
    for previous, current in zip(records[:-1], records[1:]):
        gap = (pd.Timestamp(current["date"]) - pd.Timestamp(previous["date"])).days
        rate = cash_variant_rate(policy_rate_in_force(events, previous["date"]), variant)
        yield_ = (1.0 + rate / 100.0) ** (gap / 365.0) - 1.0
        base_return = current["nav"] / previous["nav"] - 1.0
        nav.append(nav[-1] * (1.0 + base_return + float(previous["cashWeight"]) * yield_))
    return nav
