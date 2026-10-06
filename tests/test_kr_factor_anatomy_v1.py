"""Synthetic-only tests for kr-factor-anatomy-v1 (exploratory protocol + harness).

No historical price, return, label, prediction or outcome is read anywhere in this file; every number is generated here.
"""
from __future__ import annotations

import ast
from copy import deepcopy
import gzip
import json
import math
from pathlib import Path
import shutil

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import Ridge

from pipeline import kr_concentrated_portfolio as P
from pipeline import kr_factor_anatomy as A
from pipeline import kr_factor_anatomy_execution as E
from pipeline import kr_factor_anatomy_report as R
from pipeline import kr_model_overlay_portfolio as M
from pipeline import kr_model_portfolio_execution as X
from pipeline import kr_value_quality_catalyst as F
from pipeline.alpha_opportunity_model import date_weights
from pipeline.alpha_opportunity_v2_evaluation import UNRESOLVED, target_from_sessions
from pipeline.regional_alpha_features import MembershipSnapshots
from scripts import run_kr_factor_anatomy_v1 as CLI

ROOT = Path(__file__).resolve().parents[1]
INPUT_IDENTITY = "233df37ed205cc6b48828121e711417ccf961301dc58aa252430b343db9666a7"
KEPCO = "015760.KS"


def spec():
    return json.loads((ROOT / E.SPEC_PATH).read_text())


# --------------------------------------------------------------------------- #
# Synthetic panel
# --------------------------------------------------------------------------- #
def make_panel(n_dates=26, n_names=70, seed=0, nan_rate=0.1, extra=(KEPCO, "005930.KS", "000660.KS")):
    rng = np.random.default_rng(seed)
    dates = [str(d.date()) for d in pd.date_range("2016-01-08", periods=n_dates, freq="W-FRI")]
    tickers = [f"{i:06d}.KS" for i in range(1, n_names + 1)] + list(extra)
    rows = []
    for d in dates:
        for t in tickers:
            row = {"date": d, "ticker": t}
            for name in F.RAW_FEATURES:
                row[name] = float(rng.normal()) if rng.random() > nan_rate else np.nan
            row["marketCap"] = float(np.exp(rng.normal(25, 1)))
            row["adv60"] = float(np.exp(rng.normal(22, 1)))
            row["logAdv60"] = float(np.log1p(row["adv60"]))
            row["tradable"], row["coreFamilyObserved"] = True, True
            row["downsideVol126"] = float(abs(rng.normal(.3, .1)) + .02)
            row["netIncomeImprovementToAssets"] = float(rng.normal()) if rng.random() > .4 else np.nan
            row["riskMultiplier"] = [1.0, .7, .4][int(rng.integers(0, 3))]
            for h in (126, 252):
                s = str(h)
                ok = rng.random() > .05
                row["entry" + s] = str((pd.Timestamp(d) + pd.Timedelta(days=3)).date())
                row["exit" + s] = str((pd.Timestamp(d) + pd.Timedelta(days=int(h * 1.4))).date())
                row["stock" + s], row["bench" + s] = float(rng.normal(.05, .2)), float(rng.normal(.03, .1))
                row["rawStatus" + s] = "MATURED" if ok else UNRESOLVED
                row["status" + s] = row["rawStatus" + s]
                row["relObs" + s] = row["stock" + s] - row["bench" + s] if ok else np.nan
                row["rel" + s] = row["relObs" + s]
            row["fundamentalImproved126"] = bool(rng.random() > .5) if rng.random() > .3 else None
            row["logMultipleExpansion126"], row["logBookGrowth126"] = float(rng.normal()), float(rng.normal())
            rows.append(row)
    return pd.DataFrame(rows)


def make_v1(panel):
    """A synthetic stand-in for the sealed v1 predictions and fold snapshots, built with the REAL v1 transformer."""
    train = panel.copy()
    weights = date_weights(train.date)
    transformer = M.FamilyTransformer().fit(train, weights)
    x, _ = transformer.transform(train)
    y = train.rel126.fillna(0.0).to_numpy(float)
    estimator = Ridge(alpha=10.0).fit(x, y, sample_weight=weights)
    snapshot = {"activeNames": transformer.active_names, "rawCenter": [float(v) for v in transformer.raw.center],
                "rawScale": [float(v) for v in transformer.raw.scale], "interactionCenter": transformer.center.tolist(),
                "interactionScale": transformer.scale.tolist()}
    z, scores = transformer.transform(panel)
    prediction = estimator.predict(z)
    frame = panel[["date", "ticker"]].copy()
    frame["prediction"] = prediction
    for family, value in scores.items():
        frame[family + "_SCORE"] = value
    frame["rank"] = frame.groupby("date").prediction.rank(method="first", ascending=False).astype(int)
    folds = [{"horizon": h, "cutoff": "2016-01-01", "columns": transformer.columns, "coefficients": estimator.coef_.tolist(),
              "intercept": float(estimator.intercept_), "transformSnapshot": snapshot} for h in (126, 252)]
    return {"predictions": {126: frame.copy(), 252: frame.copy()}, "folds": folds}, transformer, estimator


@pytest.fixture(scope="module")
def analysis():
    s, panel = spec(), make_panel()
    v1, _, _ = make_v1(panel)
    result, rows = R.analyze_all(panel, s, v1)
    return {"spec": s, "panel": panel, "v1": v1, "result": result, "rows": rows}


# --------------------------------------------------------------------------- #
# Frozen identity and content
# --------------------------------------------------------------------------- #
def test_spec_identity_closure_and_v1_relationship():
    frozen, sha = E.load_spec()
    assert sha == (ROOT / E.SPEC_PATH).with_suffix(".sha256").read_text().strip()
    assert frozen["scientificStatus"] == "EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY"
    assert frozen["phase"] == "PROTOCOL_AND_HARNESS_ONLY_NO_OUTCOMES_COMPUTED"
    # The sealed v1 is untouched: its own loader still verifies its whole closure.
    assert X.load_spec()[1] == frozen["v1"]["specSha256"]


def test_spec_pins_exact_input_return_definition_and_boundaries():
    s = spec()
    assert s["input"]["identitySha256"] == INPUT_IDENTITY
    assert s["input"]["artifactName"] == "kr-model-raw-inputs-36844599518" and s["input"]["producingRunId"] == 36844599518
    assert s["input"]["artifactId"] == 11157875265 and s["input"]["recollectKrx"] is False
    assert s["input"]["krxCacheSha256"] == "3419d9d201f942b3c89be146b8f696679c8105a5f00d8adb0dd2c5a655a80037"
    assert s["developmentCutoff"] == "2026-09-14" and s["horizons"] == [126, 252] and s["benchmark"] == "069500.KS"
    assert s["returnDefinition"]["label"] == A.RETURN_BASIS
    assert s["returnDefinition"]["totalReturnAnalysis"] == "DATA_FOUNDATION_REQUIRED"
    assert s["returnDefinition"]["dividendAdjustment"].startswith("NONE_APPLIED")
    assert "TOTAL_RETURN" not in A.RETURN_BASIS and "TOTAL_SHAREHOLDER" not in A.RETURN_BASIS
    boundary = s["boundary"]
    assert boundary["passFailSemantics"] == "NONE" and boundary["promotionSemantics"] == "NONE"
    assert boundary["bestFactorSelection"] == "FORBIDDEN" and boundary["canRescueOrAlterKrV1"] is False
    assert s["v1"]["state"] == "DEVELOPMENT_REJECT"


def test_eleven_v1_factors_two_universes_fixed_interactions_and_cases():
    s = spec()
    assert [f["name"] for f in s["factors"]] == list(F.RAW_FEATURES) and len(s["factors"]) == 11
    assert s["universes"]["definitions"] == ["PIT_TOP120_LARGE_CAP_ANALYSIS_UNIVERSE", "PIT_TOP120_V1_INVESTABLE_ANALYSIS_UNIVERSE"]
    ids = [i["id"] for i in s["interactions"]]
    assert len(ids) == 11 and len(set(ids)) == 11
    for family in ("CHEAP_X_PROFITABILITY", "CHEAP_X_OCF_IMPROVEMENT", "CHEAP_X_PRIOR_MOMENTUM"):
        assert {i for i in ids if i.startswith(family)} == {f"{family}__B2M", f"{family}__EY", f"{family}__OCFY"}
    assert "OCF_IMPROVEMENT_X_PRIOR_RELATIVE126" in ids and "PROFITABILITY_X_OCF_IMPROVEMENT" in ids
    assert s["caseStudies"]["tickers"] == ["005930.KS", "000660.KS", "015760.KS"]
    assert s["caseStudies"]["noReplacement"] is True and s["kepco"]["ticker"] == KEPCO
    assert s["structuralClassification"]["status"] == "DATA_FOUNDATION_REQUIRED"
    assert s["structuralClassification"]["classes"] == ["REGULATED_OR_PUBLIC_ENTERPRISE", "FINANCIAL",
                                                        "ORDINARY_NON_FINANCIAL_PRIVATE"]
    neg = next(f for f in s["factors"] if f["name"] == "negativeDownsideVol126")
    assert "LOWER downside volatility" in neg["orientation"] and "LOWER" in neg["plain"]


# --------------------------------------------------------------------------- #
# Ranking, deciles, weighting
# --------------------------------------------------------------------------- #
def test_ranking_uses_only_same_date_information_and_future_data_cannot_move_ranks():
    panel = make_panel(n_dates=3, n_names=60, seed=1)
    base = A.add_signal_time_ranks(panel, ["bookToMarketProxy"])
    first = base.loc[base.date == base.date.min()]
    changed = panel.copy()
    later = changed.date > changed.date.min()
    changed.loc[later, "bookToMarketProxy"] = np.random.default_rng(9).normal(size=int(later.sum())) * 100
    future = changed.loc[changed.date == changed.date.max()].copy()
    future["date"] = "2099-01-01"
    changed = pd.concat([changed, future], ignore_index=True)
    again = A.add_signal_time_ranks(changed, ["bookToMarketProxy"])
    first_again = again.loc[again.date == again.date.min()]
    assert np.array_equal(first["bookToMarketProxy__pct"].to_numpy(), first_again["bookToMarketProxy__pct"].to_numpy(), equal_nan=True)
    assert first["bookToMarketProxy__n"].tolist() == first_again["bookToMarketProxy__n"].tolist()


def test_buckets_are_fixed_before_outcomes_and_withheld_names_keep_their_slot():
    panel = make_panel(n_dates=4, n_names=60, seed=2)
    withheld = panel.copy()
    withheld.loc[withheld.index[::3], "rel126"] = np.nan
    other = panel.copy()
    other["rel126"] = np.random.default_rng(3).normal(size=len(other))
    a = A.add_signal_time_ranks(panel, ["bookToMarketProxy"])
    b = A.add_signal_time_ranks(withheld, ["bookToMarketProxy"])
    c = A.add_signal_time_ranks(other, ["bookToMarketProxy"])
    assert a["bookToMarketProxy__pct"].equals(b["bookToMarketProxy__pct"]) and a["bookToMarketProxy__pct"].equals(c["bookToMarketProxy__pct"])
    assert A.bucket(a["bookToMarketProxy__pct"].to_numpy(), 10).tolist() == A.bucket(b["bookToMarketProxy__pct"].to_numpy(), 10).tolist()


def test_ties_share_one_percentile_and_decile_is_deterministic_under_shuffle():
    values = [1.0, 1.0, 1.0, 2.0, 3.0, np.nan]
    pct = A.pct_rank(values)
    assert pct[0] == pct[1] == pct[2] and np.isnan(pct[5])
    s = spec()
    panel = make_panel(n_dates=4, n_names=60, seed=4)
    ranked = A.add_signal_time_ranks(panel, ["earningsYieldProxy"])
    shuffled = ranked.sample(frac=1.0, random_state=7).reset_index(drop=True)
    one = A.factor_anatomy(ranked, "earningsYieldProxy", "rel126", 126, s)
    two = A.factor_anatomy(shuffled, "earningsYieldProxy", "rel126", 126, s)
    for key in ("decileMeanRelative", "decileMedianRelative", "decileBeatBenchmarkFraction", "decileObservations", "d10MinusD1",
                "meanRankCorrelation", "annualD10MinusD1"):
        assert E.json_safe(one[key]) == E.json_safe(two[key])                                  # byte-identical, not merely close


def test_each_date_counts_equally_not_each_name():
    s = spec()
    rng = np.random.default_rng(5)
    rows = []
    for date, n, y in (("2016-01-08", 100, 0.10), ("2016-01-15", 60, 0.30)):
        for i in range(n):
            rows.append({"date": date, "ticker": f"{i:06d}.KS", "x": float(rng.normal()), "y": y})
    frame = A.add_signal_time_ranks(pd.DataFrame(rows), ["x"])
    out = A.factor_anatomy(frame, "x", "y", 126, s)
    assert out["outcomeObservations"] == 160
    assert all(abs(v - 0.20) < 1e-12 for v in out["decileMeanRelative"])          # equal-date weights
    assert abs((100 * .10 + 60 * .30) / 160 - 0.20) > 0.02                          # a pooled-name mean would differ
    assert abs(out["d10MinusD1"]) < 1e-12


def ocf_names_before_half(panel):
    return int(panel.groupby("date").ocfImprovementToAssets.apply(lambda v: v.notna().sum()).min())


def test_missing_unrelated_factors_do_not_remove_a_name_from_a_standalone_anatomy():
    s = spec()
    panel = make_panel(n_dates=3, n_names=110, seed=6, nan_rate=0.0)
    panel["rel126"] = np.random.default_rng(1).normal(size=len(panel))
    panel.loc[panel.index[::2], "ocfImprovementToAssets"] = np.nan          # unrelated family missing for half the names
    ranked = A.add_signal_time_ranks(panel, ["bookToMarketProxy", "ocfImprovementToAssets"])
    book = A.factor_anatomy(ranked, "bookToMarketProxy", "rel126", 126, s)
    assert book["outcomeObservations"] == len(panel)                            # nobody dropped
    assert ocf_names_before_half(panel) >= s["statistics"]["decileMinimumNames"]
    ocf = A.factor_anatomy(ranked, "ocfImprovementToAssets", "rel126", 126, s)
    assert ocf["outcomeObservations"] == int(panel.ocfImprovementToAssets.notna().sum())


def test_dates_below_the_frozen_names_threshold_form_no_decile_table():
    s = spec()
    panel = make_panel(n_dates=3, n_names=30, seed=7, nan_rate=0.0, extra=())
    ranked = A.add_signal_time_ranks(panel, ["bookToMarketProxy"])
    out = A.factor_anatomy(ranked, "bookToMarketProxy", "rel126", 126, s)
    assert out["datesWithDeciles"] == 0 and out["datesWithRankCorrelation"] == 3 and out["outcomeObservations"] == 0
    assert A.descriptive_label(out, None, s) == "DATA_INSUFFICIENT"


# --------------------------------------------------------------------------- #
# Universes and survivorship
# --------------------------------------------------------------------------- #
def test_broad_and_v1_investable_universes_differ_only_by_the_documented_filters():
    s = spec()
    rng = np.random.default_rng(8)
    rows = []
    for i in range(400):
        rows.append({"date": "2020-01-03", "ticker": f"{i:06d}.KS", "coreFamilyObserved": bool(rng.random() > .2),
                     "tradable": bool(rng.random() > .2),
                     "adv60": [np.nan, 1e9, 3e9, 5e9][int(rng.integers(0, 4))],
                     "downsideVol126": [np.nan, .005, .01, .3][int(rng.integers(0, 4))]})
    panel = pd.DataFrame(rows)
    broad = A.universe_mask(panel, "PIT_TOP120_LARGE_CAP_ANALYSIS_UNIVERSE", s)
    investable = A.universe_mask(panel, "PIT_TOP120_V1_INVESTABLE_ANALYSIS_UNIVERSE", s)
    assert broad.all() and (investable <= broad).all()
    cfg = {"minimumAdvKrw": s["universes"]["PIT_TOP120_V1_INVESTABLE_ANALYSIS_UNIVERSE"]["v1Constraints"]["minimumAdvKrw"],
           "minimumDownsideVol": s["universes"]["PIT_TOP120_V1_INVESTABLE_ANALYSIS_UNIVERSE"]["v1Constraints"]["minimumDownsideVol"]}
    for row, flag in zip(panel.to_dict("records"), investable):
        assert bool(P.eligible(row, cfg)) == bool(flag)                         # exactly the v1 stock-eligibility rule
        if not flag:
            assert (not row["coreFamilyObserved"] or not row["tradable"] or not (row["adv60"] >= cfg["minimumAdvKrw"])
                    or not (row["downsideVol126"] >= cfg["minimumDownsideVol"]))
    with pytest.raises(ValueError, match="UNREGISTERED_UNIVERSE"):
        A.universe_mask(panel, "TODAYS_CONSTITUENTS", s)


def test_no_current_universe_or_survivorship_substitution():
    members = MembershipSnapshots([{"date": "2016-01-01", "members": ["000001.KS", "000002.KS"]},
                                   {"date": "2016-02-01", "members": ["000001.KS", "000003.KS"]}])
    good = pd.DataFrame({"date": ["2016-01-15", "2016-01-15", "2016-02-15"], "ticker": ["000001.KS", "000002.KS", "000003.KS"]})
    assert A.assert_pit_membership(good, members)
    delisted_later_is_present_earlier = good.iloc[[1]]
    assert A.assert_pit_membership(delisted_later_is_present_earlier, members)
    with pytest.raises(ValueError, match="NON_PIT_ROW"):
        A.assert_pit_membership(pd.DataFrame({"date": ["2016-02-15"], "ticker": ["000002.KS"]}), members)   # left the list
    with pytest.raises(ValueError, match="NON_PIT_ROW"):
        A.assert_pit_membership(pd.DataFrame({"date": ["2016-01-15"], "ticker": ["000003.KS"]}), members)   # today's name, not yet a member
    with pytest.raises(ValueError, match="NON_PIT_ROW"):
        A.assert_pit_membership(pd.DataFrame({"date": ["2015-06-01"], "ticker": ["000001.KS"]}), members)   # no snapshot yet


def test_withheld_outcomes_are_counted_never_zero_filled(analysis):
    denominators = analysis["result"]["denominators"]
    panel = analysis["panel"]
    year = "2016"
    block = denominators["126"][year]
    assert block["signalRows"] == len(panel)
    assert block["observedValidOutcomes"] == int(panel.rel126.notna().sum())
    assert block["v1TerminalDiscipline"].get(UNRESOLVED, 0) == int(panel.status126.eq(UNRESOLVED).sum()) > 0
    sub = R.prepare_universe(panel, R.PRIMARY_UNIVERSE, analysis["spec"])
    assert np.isnan(A.clean_numeric(sub.loc[sub.status126 == UNRESOLVED, "rel126"])).all()


# --------------------------------------------------------------------------- #
# Calendar endpoints and the return basis
# --------------------------------------------------------------------------- #
def synthetic_world(n=700):
    sessions = pd.bdate_range("2020-01-01", periods=n)
    stock = pd.DataFrame({"Close": 100 * 1.001 ** np.arange(n)}, index=sessions)
    bench = pd.DataFrame({"Close": 100 * 1.0004 ** np.arange(n)}, index=sessions)
    return sessions, {"S": stock, "B": bench}


@pytest.mark.parametrize("horizon", [126, 252])
def test_exact_endpoint_semantics_equal_the_v1_target(horizon):
    sessions, prices = synthetic_world()
    date = str(sessions[40].date())
    through = str(sessions[600].date())
    mine = A.endpoint_returns(sessions, prices, "B", "S", date, horizon, through)
    theirs = target_from_sessions(sessions, prices, "B", "S", date, horizon, through)
    assert mine["status"] == theirs["labelStatus"] == "MATURED"
    assert mine["entryDate"] == theirs["entryDate"] == str(sessions[41].date())          # next session, strictly after
    assert mine["exitDate"] == theirs["outcomeEndDate"] == str(sessions[41 + horizon].date())
    assert abs(mine["relativeReturn"] - theirs["forwardRelativeReturn"]) < 1e-15
    assert abs(mine["relativeReturn"] - (mine["stockReturn"] - mine["benchmarkReturn"])) < 1e-15
    assert mine["returnBasis"] == A.RETURN_BASIS
    pending = A.endpoint_returns(sessions, prices, "B", "S", date, horizon, str(sessions[41 + horizon - 1].date()))
    assert pending["status"] == "PENDING" and pending["relativeReturn"] is None
    broken = {k: v.copy() for k, v in prices.items()}
    broken["S"] = broken["S"].drop(index=sessions[41 + horizon])                          # no nearest-date substitution
    gap = A.endpoint_returns(sessions, broken, "B", "S", date, horizon, through)
    assert gap["status"] == UNRESOLVED and gap["relativeReturn"] is None
    assert target_from_sessions(sessions, broken, "B", "S", date, horizon, through)["labelStatus"] == UNRESOLVED
    nonpositive = {k: v.copy() for k, v in prices.items()}
    nonpositive["B"].loc[sessions[41], "Close"] = 0.0
    assert A.endpoint_returns(sessions, nonpositive, "B", "S", date, horizon, through)["status"] == UNRESOLVED
    with pytest.raises(ValueError, match="CALENDAR_TOO_SHORT"):
        A.endpoint_returns(sessions, prices, "B", "S", str(sessions[-2].date()), horizon, through)


def test_return_basis_is_never_mislabelled_total_return_and_no_dividend_adjustment_exists(analysis):
    result = analysis["result"]
    assert result["header"]["returnBasis"] == A.RETURN_BASIS == "BENCHMARK_RELATIVE_ADJUSTED_INDEX_RETURN_PARTIAL_DISTRIBUTIONS"
    assert result["header"]["totalReturnAnalysis"] == "DATA_FOUNDATION_REQUIRED"
    assert result["header"]["dividendAdjustment"] == "NONE_APPLIED"
    text = json.dumps(E.json_safe(result))
    assert "TOTAL_SHAREHOLDER_RETURN" not in text
    report = R.render_report(result, analysis["spec"])
    assert "neither a pure price return nor a complete total shareholder return" in report
    assert "DATA_FOUNDATION_REQUIRED" in report
    for module in ("kr_factor_anatomy.py", "kr_factor_anatomy_report.py", "kr_factor_anatomy_execution.py"):
        source = (ROOT / "pipeline" / module).read_text()
        assert "to_total_return" not in source and "Dividends" not in source          # nothing fabricates an adjustment


# --------------------------------------------------------------------------- #
# Strata, interactions, fundamentals vs price
# --------------------------------------------------------------------------- #
def test_stratified_association_reads_the_within_stratum_relationship():
    s = spec()
    rng = np.random.default_rng(10)
    rows = []
    for d in range(12):
        for i in range(100):
            cap = float(rng.normal())
            x = float(rng.normal())
            sign = 1 if cap > 0 else -1                                    # factor helps in upper strata, hurts in lower
            rows.append({"date": f"2016-{d + 1:02d}-05", "ticker": f"{i:06d}.KS", "cap": cap, "x": x,
                         "y": sign * x + .1 * float(rng.normal())})
    out = A.stratified_association(pd.DataFrame(rows), "x", "cap", "y", s)
    table = out["table"]
    assert table["1"]["meanRankCorrelation"] < -0.5 and table["5"]["meanRankCorrelation"] > 0.5
    assert A.strata_agreement(table, 1)["agreeing"] < A.strata_agreement(table, 1)["measured"]


def test_interactions_use_frozen_same_date_cutoffs_independent_of_outcomes():
    s = spec()
    panel = make_panel(n_dates=5, n_names=60, seed=11, nan_rate=0.0)
    item = next(i for i in s["interactions"] if i["id"] == "CHEAP_X_OCF_IMPROVEMENT__B2M")
    day = panel.loc[panel.date == panel.date.min()]
    ga = A.axis_groups(day, item["a"]["column"], item["a"]["rule"], s["statistics"])
    gb = A.axis_groups(day, item["b"]["column"], item["b"]["rule"], s["statistics"])
    altered = day.copy()
    altered["rel126"] = np.random.default_rng(1).normal(size=len(altered))
    assert ga.tolist() == A.axis_groups(altered, item["a"]["column"], item["a"]["rule"], s["statistics"]).tolist()
    assert set(ga.tolist()) == {0, 1, 2} and set(gb.tolist()) == {0, 1}
    assert (gb == (day.ocfImprovementToAssets.to_numpy() > 0).astype(int)).all()
    assert A.bucket([0.3333, 0.34, 0.6666, 0.67], 3).tolist() == [0, 1, 1, 2]       # 1/3 and 2/3 are the only cutoffs
    table = A.interaction_table(panel, item["a"], item["b"], "rel126", s)
    assert table["axisA"]["rule"] == {"kind": "terciles"} and table["axisB"]["rule"] == {"kind": "binaryPositive"}
    assert all(c["names"] >= s["statistics"]["interactionCellMinimumNames"] for c in table["cells"].values())
    assert len(table["cells"]) == 6


def test_four_states_partition_the_observations_and_describe_the_miss_composition():
    s = spec()
    rng = np.random.default_rng(12)
    rows = []
    for d in range(6):
        for i in range(90):
            up = bool(rng.random() > .5)
            run_up = float(rng.normal())
            # fundamentals-up names that ran up a lot tend to miss: a composition the table must surface, not explain
            y = float(rng.normal() * .05 - (0.2 if up and run_up > .5 else -0.05))
            rows.append({"date": f"2016-{d + 1:02d}-05", "ticker": f"{i:06d}.KS", "up": up, "relative126": run_up, "rel": y})
    table = A.four_state_table(pd.DataFrame(rows), "up", "rel", strata={"RUNUP": {"column": "relative126"}}, spec=s)
    assert table["status"] == "DESCRIPTIVE" and abs(sum(table["shareByState"].values()) - 1.0) < 1e-12
    assert set(table["shareByState"]) == set(A.STATES) and table["causalReading"] == "NONE"
    comp = table["compositionOfFundamentalsUpPriceDown"]["RUNUP"]
    assert comp["2"]["shareOfFundamentalsUpPriceDown"] > comp["2"]["shareOfAllFundamentalsUp"]
    none = A.four_state_table(pd.DataFrame({"date": ["2016-01-05"] * 3, "up": [None] * 3, "rel": [1., 2., 3.]}), "up", "rel")
    assert none["status"] == "DATA_INSUFFICIENT"


def test_net_income_improvement_reproduces_the_v1_ocf_chain_and_abstains_on_mixed_basis():
    def filing(year, stage, ni, ocf, basis="CFS", assets=200):
        available = {"11011": f"{year + 1}-03-20", "11013": f"{year}-05-15", "11012": f"{year}-08-14", "11014": f"{year}-11-14"}[stage]
        accounts = {}
        for name, value, statement in (("당기순이익", ni, "IS"), ("영업활동현금흐름", ocf, "CF"),
                                      ("자산총계", assets, "BS"), ("부채총계", 50, "BS")):
            accounts[name] = {"amounts": {"thstrm_amount": value, "thstrm_add_amount": value}, "statement": statement}
        return {"id": f"f:{year}:{stage}", "ticker": "000001.KS", "fiscalYear": year, "reportCode": stage,
                "availableFrom": available, "receiptNos": [available.replace("-", "") + "000001"], "fsDiv": basis,
                "accounts": accounts}
    records = [filing(2018, "11011", 40, 70), filing(2019, "11011", 55, 95), filing(2019, "11014", 41, 71),
               filing(2018, "11014", 30, 50), filing(2020, "11014", 60, 120)]
    date = "2021-01-04"
    values, _ = F.accounting_values(records, date)
    expected_ocf = F.ratio(values["ocfTtm"] - values["priorOcfTtm"], values["assets"])
    assert E.improvement_to_assets(records, date, "영업활동현금흐름") == expected_ocf
    ni = E.improvement_to_assets(records, date, "당기순이익")
    assert ni is not None and math.isfinite(ni)
    mixed = [dict(r, fsDiv="OFS") if r["fiscalYear"] == 2018 else r for r in records]
    assert E.improvement_to_assets(mixed, date, "당기순이익") is None                    # one statement basis or nothing
    assert E.improvement_to_assets(records[:1], "2019-03-01", "당기순이익") is None        # nothing visible


# --------------------------------------------------------------------------- #
# Descriptive labels, intervals, year views
# --------------------------------------------------------------------------- #
def anatomy(**over):
    base = {"datesWithDeciles": 300, "decileMonotonicity": 0.9, "d10MinusD1": 0.02, "meanRankCorrelation": 0.05, "leaveBestYearOut": {"signRetained": True},
            "spreadYearStability": {"positiveYearFraction": 0.9}}
    base.update(over)
    return base


def test_descriptive_labels_are_rule_based_and_exhaustive():
    s = spec()
    agree = {"measured": 5, "agreeing": 5}
    assert A.descriptive_label(anatomy(), agree, s) == "BROADLY_POSITIVE_HISTORICAL_ASSOCIATION"
    assert A.descriptive_label(anatomy(d10MinusD1=-.02, decileMonotonicity=-.9, meanRankCorrelation=-.05,
                                       spreadYearStability={"positiveYearFraction": .1}), agree, s) == \
        "BROADLY_NEGATIVE_HISTORICAL_ASSOCIATION"
    assert A.descriptive_label(anatomy(decileMonotonicity=.2), agree, s) == "NO_CLEAR_MONOTONIC_PATTERN"
    assert A.descriptive_label(anatomy(spreadYearStability={"positiveYearFraction": .5}), agree, s) == "UNSTABLE_OR_REGIME_DEPENDENT"
    assert A.descriptive_label(anatomy(leaveBestYearOut={"signRetained": False}), agree, s) == "UNSTABLE_OR_REGIME_DEPENDENT"
    assert A.descriptive_label(anatomy(), {"measured": 5, "agreeing": 3}, s) == "CONCENTRATED_IN_SPECIFIC_STRATA"
    assert A.descriptive_label(anatomy(datesWithDeciles=10), agree, s) == "DATA_INSUFFICIENT"
    assert A.descriptive_label(anatomy(), {"measured": 1, "agreeing": 1}, s) == "DATA_INSUFFICIENT"
    assert set(s["interpretation"]["labels"]) == set(A.DESCRIPTIVE_LABELS)


@pytest.mark.parametrize("over", [
    {"d10MinusD1": .02, "decileMonotonicity": .9, "meanRankCorrelation": -.05},     # rank correlation contradicts
    {"d10MinusD1": .02, "decileMonotonicity": -.9, "meanRankCorrelation": .05},     # monotonicity contradicts
    {"d10MinusD1": -.02, "decileMonotonicity": .9, "meanRankCorrelation": .05},     # spread contradicts
    {"d10MinusD1": -.02, "decileMonotonicity": .9, "meanRankCorrelation": -.05,
     "spreadYearStability": {"positiveYearFraction": .1}},
    {"d10MinusD1": .02, "decileMonotonicity": .9, "meanRankCorrelation": 0.0},      # a measure with no direction
    {"d10MinusD1": .02, "decileMonotonicity": .9, "meanRankCorrelation": None},
])
def test_contradictory_direction_measures_never_give_a_broad_label(over):
    s = spec()
    label = A.descriptive_label(anatomy(**over), {"measured": 5, "agreeing": 5}, s)
    assert label == "NO_CLEAR_MONOTONIC_PATTERN"
    assert label not in ("BROADLY_POSITIVE_HISTORICAL_ASSOCIATION", "BROADLY_NEGATIVE_HISTORICAL_ASSOCIATION")


def test_canonical_direction_is_the_spread_sign_and_is_frozen():
    s = spec()["interpretation"]
    assert "D10-D1" in s["canonicalDirection"] and len(s["directionMeasures"]) == 3
    assert A.canonical_sign(anatomy(d10MinusD1=-.01)) == -1 and A.canonical_sign(anatomy(d10MinusD1=0.0)) == 0
    assert A.direction_measures(anatomy())["consistent"] is True
    assert A.direction_measures(anatomy(meanRankCorrelation=-.1))["consistent"] is False


def test_scope_is_large_cap_everywhere_and_investigation_is_frozen():
    s = spec()
    assert "TOP-120" in s["universes"]["scopeStatement"] and "LARGE CAP" in s["universes"]["scopeStatement"]
    assert "BROAD_PIT_ANALYSIS_UNIVERSE" not in json.dumps(s)
    inv = s["universes"]["scopeInvestigation"]
    assert "NOT broadened" in inv["marketOnlyFactors"] and "NOT broadened" in inv["accountingFactors"]
    audit = json.loads((ROOT / "docs/results/kr-factor-anatomy-v1-input-scope-audit.json").read_text())
    assert audit["readsNoPriceLevelReturnLabelOrOutcome"] is True
    assert audit["pricePanels"]["equalsSecuritiesEverInTop120"] is True and audit["accounting"]["outsideEverTop120"] == 0
    assert audit["universe"]["distinctSecuritiesRank1To120"] == 260 and audit["universe"]["distinctSecuritiesRank1To300"] == 624


def test_financial_case_studies_are_frozen_with_caveats_and_structure_stays_blocked():
    s = spec()
    fin = s["financialCaseStudies"]
    assert len(fin["tickers"]) == 8 and "105560.KS" in fin["tickers"] and set(fin["names"]) == set(fin["tickers"])
    assert fin["distributionCaveats"] and all(v["hasSealedPricePanel"] for v in fin["inputCoverageAtFreeze"].values())
    assert s["structuralClassification"]["status"] == "DATA_FOUNDATION_REQUIRED"
    assert s["structuralClassification"]["investigation"]["attemptedBeforeOutcomes"] is True
    assert "015760.KS" not in fin["tickers"] and s["kepco"]["primaryUniverse"].startswith("KEPCO is NOT excluded")


def test_block_interval_is_deterministic_descriptive_and_refuses_short_series():
    s = spec()["uncertainty"]
    short = A.block_interval_columns(np.random.default_rng(0).normal(size=(40, 3)), 26, s)
    assert short["status"] == "DATA_INSUFFICIENT"
    series = np.random.default_rng(1).normal(size=(260, 3))
    one, two = A.block_interval_columns(series, 26, s), A.block_interval_columns(series, 26, s)
    assert one == two and one["status"] == "DESCRIPTIVE" and one["calibrated"] is False and one["multiplicityAdjusted"] is False
    assert all(lo <= est <= hi for lo, est, hi in zip(one["lower"], one["estimate"], one["upper"]))
    assert s["blockDates"] == {"126": 26, "252": 52} and s["seed"] == 42 and s["replicates"] == 2000


def test_year_table_and_leave_best_year_out():
    s = spec()["statistics"]
    rows = [{"date": f"{y}-01-{d:02d}", "year": y, "spread": v} for y, vals in
            ((2016, [1.0] * 14), (2017, [-.1] * 14), (2018, [-.1] * 14), (2019, [-.1] * 3)) for d, v in enumerate(vals, 1)]
    table, stability = A.year_table(rows, "spread", s)
    assert stability["eligibleYears"] == 3 and stability["positiveYears"] == 1 and "2019" in table        # short year tabulated, not counted
    leave = A.leave_best_year_out(rows, "spread")
    assert leave["droppedYear"] == 2016 and leave["signRetained"] is False


# --------------------------------------------------------------------------- #
# Mechanical winners, losers and fixed case studies
# --------------------------------------------------------------------------- #
def events_frame(n=200, seed=13):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        t = f"{int(rng.integers(0, 12)):06d}.KS"
        d = str((pd.Timestamp("2016-01-01") + pd.Timedelta(days=int(rng.integers(0, 600)))).date())
        stock = float(rng.normal(0, .3))
        rows.append({"date": d, "ticker": t, "entryDate": d, "exitDate": str((pd.Timestamp(d) + pd.Timedelta(days=180)).date()),
                     "stockReturn": stock, "benchmarkReturn": 0.03, "relativeReturn": stock - .03,
                     "prediction": float(rng.normal(0, .05)), "predictionError": float(rng.normal(0, .2))})
    return pd.DataFrame(rows)


def test_winner_loser_selection_is_mechanical_deterministic_and_non_overlapping():
    s = spec()
    events = events_frame()
    first = A.mechanical_event_tables(events, s)
    second = A.mechanical_event_tables(events.sample(frac=1.0, random_state=3).reset_index(drop=True), s)
    assert set(first) == {"largestPositiveStockReturn", "largestNegativeStockReturn", "largestAbsoluteStockReturn", "benchmarkRelativeWinners", "benchmarkRelativeLosers",
                          "largestPositivePredictionError", "largestNegativePredictionError"}
    for name, table in first.items():
        assert len(table) <= s["winnersLosers"]["count"]
        again = second[name]
        assert table[["date", "ticker"]].values.tolist() == again[["date", "ticker"]].values.tolist()
        for _, group in table.groupby("ticker"):
            spans = sorted(zip(group.entryDate, group.exitDate))
            assert all(a[1] < b[0] for a, b in zip(spans, spans[1:]))                       # no overlapping windows per ticker
    winners = first["benchmarkRelativeWinners"].relativeReturn.tolist()
    assert winners == sorted(winners, reverse=True)
    assert first["benchmarkRelativeLosers"].relativeReturn.tolist() == sorted(first["benchmarkRelativeLosers"].relativeReturn)
    assert first["largestAbsoluteStockReturn"].stockReturn.abs().is_monotonic_decreasing
    assert first["largestPositiveStockReturn"].stockReturn.is_monotonic_decreasing
    assert first["largestNegativeStockReturn"].stockReturn.is_monotonic_increasing
    assert first["largestPositiveStockReturn"].stockReturn.iloc[0] >= first["largestNegativeStockReturn"].stockReturn.iloc[0]


def test_top_five_frequency_and_fixed_case_selection():
    s = spec()
    predictions = pd.DataFrame({"date": ["d1"] * 6 + ["d2"] * 6, "ticker": list("ABCDEF") * 2,
                                "rank": [1, 2, 3, 4, 5, 6, 2, 1, 3, 4, 5, 6]})
    top = A.top5_frequency(predictions, s)
    assert top.iloc[0].topFiveDates == 2 and "F" not in set(top.ticker)
    events = pd.DataFrame({"ticker": [KEPCO] * 4 + ["005930.KS"], "date": ["2018-01-05", "2018-02-02", "2018-03-02", "2018-04-06", "2018-01-05"],
                           "prediction": [.1, -.2, .3, 0.0, .05], "relativeReturn": [.1, .1, -.5, .4, 0.0],
                           "predictionError": [.0, .3, -.8, .4, -.05]})
    picked = A.case_selection(events, KEPCO)
    assert picked["highestPrediction"].date == "2018-03-02" and picked["lowestPrediction"].date == "2018-02-02"
    assert picked["largestPositiveError"].date == "2018-04-06" and picked["largestNegativeError"].date == "2018-03-02"
    assert A.case_selection(events, "000660.KS") == {"status": "NO_DATA", "ticker": "000660.KS"}        # never replaced by another firm


def test_v1_prediction_decomposition_is_reconstructed_exactly_from_the_fold_snapshot():
    panel = make_panel(n_dates=6, n_names=60, seed=14, nan_rate=0.2)
    v1, transformer, estimator = make_v1(panel)
    fold = v1["folds"][0]
    prediction = v1["predictions"][126]
    for index in (0, 7, 90, len(panel) - 1):
        row = panel.iloc[index].to_dict()
        archived = float(prediction.iloc[index].prediction)
        out = A.reconstruct_prediction(row, fold, archived=archived)
        assert out["status"] == "RECONSTRUCTED"
        assert abs(out["prediction"] - archived) < 1e-9
        assert abs(out["intercept"] + sum(out["contributions"].values()) - archived) < 1e-9
        assert set(out["interactionContributions"]) == set(M.INTERACTIONS)
        scores = {f: float(prediction.iloc[index][f + "_SCORE"]) for f in F.FAMILIES}
        assert all(abs(out["familyScores"][f] - scores[f]) < 1e-9 for f in F.FAMILIES)
    bad = A.reconstruct_prediction(panel.iloc[0].to_dict(), fold, archived=float(prediction.iloc[0].prediction) + 0.01)
    assert bad["status"] == "MISMATCH" and "contributions" not in bad                          # never approximated


# --------------------------------------------------------------------------- #
# End-to-end assembly on synthetic data
# --------------------------------------------------------------------------- #
def test_assembly_keeps_kepco_in_the_primary_universe_and_reports_a_separate_labelled_leave_out(analysis):
    result, panel, s = analysis["result"], analysis["panel"], analysis["spec"]
    sub = R.prepare_universe(panel, R.PRIMARY_UNIVERSE, s)
    assert (sub.ticker == KEPCO).sum() == (panel.ticker == KEPCO).sum() > 0
    primary = result["universes"][R.PRIMARY_UNIVERSE]["standalone"][R.V1_DISCIPLINE]["bookToMarketProxy"]["126"]
    leave = result["kepco"]
    assert leave["fullUniverseIncludesKepco"] is True and leave["removedRows"] == int((panel.ticker == KEPCO).sum())
    assert leave["status"] == "SINGLE_TICKER_LEAVE_OUT_NOT_A_CLASSIFICATION_CLAIM"
    cut = leave["leaveKepcoOutStandalone"]["bookToMarketProxy"]["126"]
    assert cut["outcomeObservations"] < primary["outcomeObservations"]


def test_structural_classification_is_a_data_foundation_gate_and_cannot_appear_after_outcomes(analysis, tmp_path):
    s = deepcopy(analysis["spec"])
    assert A.structural_status(s, tmp_path) == {"status": "DATA_FOUNDATION_REQUIRED", "subgroupTables": "DATA_FOUNDATION_REQUIRED"}
    path = tmp_path / s["structuralClassification"]["classificationPath"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"REGULATED_OR_PUBLIC_ENTERPRISE": [KEPCO]}))
    with pytest.raises(ValueError, match="UNPINNED_STRUCTURAL_CLASSIFICATION_PRESENT"):          # a list added after the spec
        A.structural_status(s, tmp_path)
    s["structuralClassification"].update(status="PASSED", classificationSha256="0" * 64)
    with pytest.raises(ValueError, match="STRUCTURAL_CLASSIFICATION_MISSING_OR_CHANGED"):
        A.structural_status(s, tmp_path)
    s["structuralClassification"]["classificationSha256"] = E.digest(json.loads(path.read_text()))
    assert A.structural_status(s, tmp_path)["status"] == "PASSED"
    result = analysis["result"]
    assert result["structuralClassification"]["subgroupTables"] == "DATA_FOUNDATION_REQUIRED"
    assert not any("sector" in k.lower() or ("financial" in k.lower() and k != "financialCaseStudies") for k in result)


def test_every_frozen_table_is_produced_for_both_horizons_and_universes(analysis):
    result, s = analysis["result"], analysis["spec"]
    for universe in (R.PRIMARY_UNIVERSE, R.SECONDARY_UNIVERSE):
        block = result["universes"][universe]
        assert set(block["standalone"][R.V1_DISCIPLINE]) == set(F.RAW_FEATURES)
        for factor in F.RAW_FEATURES:
            assert set(block["standalone"][R.V1_DISCIPLINE][factor]) == {"126", "252"}
        assert set(block["interactions"]) == {i["id"] for i in s["interactions"]}
        assert set(block["sizeLiquidity"]["126"]["marketCapStrata"]) == set(F.RAW_FEATURES)
        assert block["sizeLiquidity"]["126"]["adv60Strata"]["logAdv60"]["status"].startswith("NOT_APPLICABLE")
        assert set(block["sizeLiquidity"]["126"]["liquidityViews"]) == {"rawAdvRankVsFutureReturn", "advEffectWithinMarketCapStrata",
                                                                       "marketCapEffectWithinAdvStrata"}
        assert set(block["fundamentalsVsPrice"]["signalTime"]) == {"ocfImprovementUp", "netIncomeImprovementUp"}
        assert [row["factor"] for row in block["labelsAndExecutiveMap"]] == list(F.RAW_FEATURES)     # spec order, never sorted by result
        assert set(block["families"]) >= {f + "_RANKMEAN" for f in F.FAMILIES}
        assert {c for c in block["families"] if "_V1_H" in c}                                      # archived v1 family scores
    assert R.ALL_OBSERVED in result["universes"][R.PRIMARY_UNIVERSE]["standalone"]
    assert R.ALL_OBSERVED not in result["universes"][R.SECONDARY_UNIVERSE]["standalone"]
    assert set(result["winnersLosers"]["126"]) >= {"benchmarkRelativeWinners", "benchmarkRelativeLosers", "largestAbsoluteStockReturn",
                                                  "largestPositivePredictionError", "largestNegativePredictionError", "mostFrequentV1TopFive"}


def test_case_studies_use_the_fixed_firms_and_exact_decompositions(analysis):
    cases = analysis["result"]["caseStudies"]
    assert list(cases) == ["005930.KS", "000660.KS", "015760.KS"]
    for ticker, case in cases.items():
        assert case["status"] == "SELECTED"
        for key in ("highestPrediction", "lowestPrediction", "largestPositiveError", "largestNegativeError"):
            event = case[key]
            assert event["ticker"] == ticker and event["v1Decomposition"]["status"] == "RECONSTRUCTED"
            assert len(event["rawFeatures"]) == 11 and len(event["withinDatePercentile"]) == 11
            assert abs(event["v1Decomposition"]["prediction"] - event["prediction"]) < 1e-8
            assert event["relativeReturn"] == pytest.approx(event["stockReturn"] - event["benchmarkReturn"])


def test_no_pass_fail_promotion_best_factor_or_weight_anywhere_in_the_output(analysis):
    result = analysis["result"]
    assert A.assert_no_forbidden_keys(result)
    text = json.dumps(E.json_safe(result))
    for banned in ('"PASS"', '"FAIL"', "productionReady", "promotionEligible", "bestFactor", "recommendedPortfolio", "factorWeight"):
        assert banned not in text
    for row in result["universes"][R.PRIMARY_UNIVERSE]["labelsAndExecutiveMap"]:
        for h in row["horizons"].values():
            assert h["descriptiveLabel"] in A.DESCRIPTIVE_LABELS
    for bad in ({"promotionEligible": True}, {"a": {"bestFactor": "x"}}, {"x": [{"verdict": "PASS"}]}):
        with pytest.raises(ValueError, match="FORBIDDEN_OUTPUT_KEY"):
            A.assert_no_forbidden_keys(bad)
    assert spec()["interpretation"]["forbiddenOutputs"]


def test_outputs_are_deterministic_gzip_stable_and_nan_free(analysis, tmp_path):
    s = analysis["spec"]
    counters = E.Counters()
    manifests = []
    for name in ("one", "two"):
        manifests.append(E.write_outputs(tmp_path / name, analysis["result"], analysis["rows"], R.render_report(analysis["result"], s),
                                         s, "f" * 64, {"sha256": INPUT_IDENTITY}, counters))
    assert manifests[0] == manifests[1]
    one, two = tmp_path / "one", tmp_path / "two"
    for rel in manifests[0]["files"]:
        assert (one / rel).read_bytes() == (two / rel).read_bytes()
    assert manifests[0]["returnBasis"] == A.RETURN_BASIS and manifests[0]["counters"] == dict.fromkeys(
        ("targetCalls", "labelCalls", "predictionRecordReads", "anatomyOutcomeCalls"), 0)
    text = (one / "anatomy.json").read_text()
    assert "NaN" not in text and "Infinity" not in text
    table = next(p for p in (one / "tables").glob("*.csv.gz"))
    assert pd.read_csv(table).shape[0] > 0 and gzip.open(table).read(2)
    assert E.json_safe({"a": float("nan"), "b": np.float64("inf"), "c": np.int64(3)}) == {"a": None, "b": None, "c": 3}


# --------------------------------------------------------------------------- #
# Authorization: outcome execution only from merged main
# --------------------------------------------------------------------------- #
def fake_git(head="abc123", override=None):
    def git(args, cwd):
        if args == ["rev-parse", "HEAD"]:
            return (head + "\n").encode()
        if args[0] == "show":
            rel = args[1].split(":", 1)[1]
            return override if override is not None else (Path(cwd) / rel).read_bytes()
        raise AssertionError(args)
    return git


def good_env(s):
    return {"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_SHA": "abc123", "ANATOMY_INPUT_ARTIFACT": s["input"]["artifactName"],
            "ANATOMY_INPUT_RUN_ID": str(s["input"]["producingRunId"])}


def unsealed_repo(tmp_path):
    """A synthetic PRE-SEAL repository: exact copies of the frozen spec and sidecar, and NO committed result. The real
    ROOT may or may not carry the sealed result, so lifecycle behaviour is never asserted against it."""
    repo = tmp_path / "repo"
    for rel in (E.SPEC_PATH, str(Path(E.SPEC_PATH).with_suffix(".sha256"))):
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, repo / rel)
    assert not (repo / E.RESULT_PATH).exists()
    return repo


def test_outcome_execution_refuses_before_merged_main_authorization_and_spec_seal(tmp_path):
    s, sha = E.load_spec()
    env = good_env(s)
    repo = unsealed_repo(tmp_path)
    permit = E.authorize_execution(s, sha, repo, env, fake_git())                      # pre-seal state: authorized
    assert isinstance(permit, E.ExecutionPermit) and permit.specSha256 == sha
    cases = [({"GITHUB_ACTIONS": "false"}, "REQUIRES_ACTIONS"), ({"GITHUB_REF": "refs/heads/feature"}, "REQUIRES_MAIN"),
             ({"GITHUB_REF": "refs/pull/1/merge"}, "REQUIRES_MAIN"),
             ({"GITHUB_EVENT_NAME": "pull_request"}, "REQUIRES_WORKFLOW_DISPATCH"), ({"GITHUB_EVENT_NAME": "push"}, "REQUIRES_WORKFLOW_DISPATCH"),
             ({"GITHUB_SHA": "other"}, "NOT_THE_DISPATCHED_COMMIT"), ({"GITHUB_SHA": ""}, "NOT_THE_DISPATCHED_COMMIT"),
             ({"ANATOMY_INPUT_ARTIFACT": "kr-model-raw-replay-36876869657"}, "INPUT_ARTIFACT_IDENTITY_MISMATCH"),
             ({"ANATOMY_INPUT_RUN_ID": "36876869657"}, "INPUT_ARTIFACT_IDENTITY_MISMATCH"),
             ({"ANATOMY_INPUT_RUN_ID": ""}, "INPUT_ARTIFACT_IDENTITY_MISMATCH")]
    for change, message in cases:
        with pytest.raises(ValueError, match=message):
            E.authorize_execution(s, sha, repo, {**env, **change}, fake_git())
    with pytest.raises(ValueError, match="SPEC_NOT_COMMITTED_AT_HEAD"):                 # unmerged / edited spec
        E.authorize_execution(s, sha, repo, env, fake_git(override=b"{}"))
    (repo / E.RESULT_PATH).parent.mkdir(parents=True, exist_ok=True)                    # the result is now committed
    (repo / E.RESULT_PATH).write_text("{}")
    with pytest.raises(ValueError, match="ANATOMY_RESULT_ALREADY_COMMITTED"):
        E.authorize_execution(s, sha, repo, env, fake_git())


def test_every_outcome_path_refuses_without_a_permit_and_before_any_data_is_read(monkeypatch, tmp_path):
    s, sha = E.load_spec()
    def bomb(*a, **k):
        raise AssertionError("data read before authorization")
    for name in ("prepare", "input_identity", "load_sources", "build_labels", "replay_portfolio", "issue_permit", "claim_execution_lock"):
        monkeypatch.setattr(X, name, bomb)
    counters = E.Counters()
    for call in (lambda: E.build_panel({}, {}, s, None, counters), lambda: E.read_v1(ROOT, s, None, counters),
                 lambda: E.execute(tmp_path / "missing", tmp_path / "out", s, sha, None)):
        with pytest.raises(ValueError, match="ANATOMY_OUTCOME_ACCESS_WITHOUT_PERMIT"):
            call()
    with pytest.raises(ValueError, match="ANATOMY_OUTCOME_ACCESS_WITHOUT_PERMIT"):
        E.execute(tmp_path / "missing", tmp_path / "out", s, sha, E.ExecutionPermit(sha, object()))        # forged permit
    with pytest.raises(ValueError, match="FORMAL_EXECUTION_REQUIRES_ACTIONS"):
        CLI.run("execute", input_root=str(tmp_path / "missing"), output=str(tmp_path / "out"), env={})
    with pytest.raises(ValueError, match="UNREGISTERED_EXECUTION_MODE"):
        CLI.run("gates-only")
    assert counters.zero()


def test_verify_is_outcome_free_and_pull_request_ci_runs_only_verify(monkeypatch, tmp_path):
    def bomb(*a, **k):
        raise AssertionError("verify touched data")
    for name in ("prepare", "input_identity", "load_sources"):
        monkeypatch.setattr(X, name, bomb)
    report = CLI.run("verify", output=str(tmp_path), env={})
    assert report["status"] == "VERIFIED" and report["stoppedBeforeOutcomes"] is True and report["historicalExecutionPerformed"] is False
    assert report["executeAuthorizedInThisEnvironment"] is False
    assert all(v == 0 for v in report["counters"].values()) and (tmp_path / "verify.json").is_file()
    workflow = (ROOT / ".github/workflows/kr-factor-anatomy-v1.yml").read_text()
    frozen, execute = workflow.split("\n  execute:")
    assert "--mode execute" not in frozen and "--mode verify" in frozen
    assert workflow.count("--mode execute") == 1
    assert "if: github.event_name == 'workflow_dispatch' && inputs.mode == 'execute'" in execute
    for needle in ("refs/heads/main", "getArtifact", "a.digest", "SPEC_NOT_COMMITTED_AT_HEAD", "needs: frozen-machine",
                   "ANATOMY_ALREADY_SEALED", "download-artifact", "run-id: ${{ inputs.inputRunId }}"):
        assert needle in execute
    on_block = workflow.split("permissions:")[0]
    assert "pull_request:" in on_block and "workflow_dispatch:" in on_block
    assert "permissions:\n  contents: read\n  actions: read" in workflow
    for forbidden in ("kr-model-overlay-portfolio-v1.yml", "gh workflow", "createWorkflowDispatch", "KRX_", "collect_", "secrets.KRX", "contents: write"):
        assert forbidden not in workflow


def test_modules_never_touch_the_network_the_v1_execute_path_or_other_outcome_engines():
    banned_names = {"build_labels", "model_predictions", "evaluate_model", "replay_portfolio", "run_historical", "issue_permit",
                    "claim_execution_lock", "require_authorization", "urlopen", "Request"}
    banned_imports = {"requests", "urllib", "socket", "http", "yfinance", "FinanceDataReader", "subprocess_run_gh"}
    for path in (ROOT / "pipeline/kr_factor_anatomy.py", ROOT / "pipeline/kr_factor_anatomy_report.py",
                 ROOT / "pipeline/kr_factor_anatomy_execution.py", ROOT / "scripts/run_kr_factor_anatomy_v1.py"):
        tree = ast.parse(path.read_text())
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        assert not (names & banned_names), (path.name, names & banned_names)
        imported = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        imported |= {(n.module or "").split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.level == 0}
        assert not (imported & banned_imports), (path.name, imported & banned_imports)


# --------------------------------------------------------------------------- #
# Literal copies of sealed conventions are proved equal to the sealed originals
# --------------------------------------------------------------------------- #
def test_local_copies_of_sealed_conventions_equal_the_sealed_originals():
    from pipeline import alpha_opportunity_model as sealed_model
    from pipeline import alpha_opportunity_v2_evaluation as sealed_eval
    from pipeline import alpha_opportunity_spec as sealed_spec
    assert (A.MATURED, A.PENDING, A.UNRESOLVED) == (sealed_eval.MATURED, sealed_eval.PENDING, sealed_eval.UNRESOLVED)
    for n, block in ((200, 26), (312, 52), (60, 26)):
        for seed in (0, 42, 7):
            ours = A.moving_block_indices(n, block, np.random.default_rng(seed))
            theirs = sealed_model.block_sample_indices(n, block, np.random.default_rng(seed))
            assert ours.tolist() == theirs.tolist()
    with pytest.raises(ValueError, match="DATA_INSUFFICIENT_BLOCKS"):
        A.moving_block_indices(10, 26, np.random.default_rng(0))
    assert A.digest({"a": 1}) == sealed_spec.digest({"a": 1}) and E.file_hash(ROOT / E.SPEC_PATH) == sealed_spec.file_hash(ROOT / E.SPEC_PATH)


def test_only_the_two_registered_sealed_v1_functions_resolve_and_no_production_module_imports_the_anatomy():
    assert E.sealed_v1_function("target_from_sessions") is target_from_sessions
    assert E.sealed_v1_function("attach_eligibility").__module__.endswith("alpha_opportunity_v4_execution")
    for name in ("replay_portfolio", "build_labels", "fit", "issue_permit", ""):
        with pytest.raises(ValueError, match="UNREGISTERED_SEALED_FUNCTION"):
            E.sealed_v1_function(name)
    mine = {"kr_factor_anatomy", "kr_factor_anatomy_report", "kr_factor_anatomy_execution"}
    for path in (ROOT / "pipeline").glob("*.py"):
        if path.stem in mine or path.stem.startswith(("kr_top120_regime_review", "kr_industry_anatomy", "kr_stock_within_industry_anatomy", "kr_market_risk_anatomy", "kr_integrated_alpha_portfolio", "kr_alpha_tournament")):        # the exploratory successors reuse, never replace
            continue
        tree = ast.parse(path.read_text())
        imported = {a.name.split(".")[-1] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        imported |= {(n.module or "").split(".")[-1] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        imported |= {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
        assert not (imported & mine), path.name
