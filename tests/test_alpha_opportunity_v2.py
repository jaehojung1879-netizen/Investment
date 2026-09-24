"""alpha-opportunity-model-v2 contract tests. Synthetic fixtures only.

Nothing here reads a real replay price, builds a real label, or fits a model on
real data. The economic contract under test: the regional benchmark is an
explicit outside option with net alpha 0, the number of active names is
endogenous (possibly zero), and nothing in the signal layer sizes a position.
"""
from __future__ import annotations

import ast
from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pipeline import alpha_opportunity_features as F
from pipeline import alpha_opportunity_model as V1M
from pipeline import alpha_opportunity_spec as V1S
from pipeline import alpha_opportunity_v2_decision as D
from pipeline import alpha_opportunity_v2_evaluation as E
from pipeline import alpha_opportunity_v2_model as M
from pipeline import alpha_opportunity_v2_spec as S
from pipeline import pit_data
from pipeline import replay_calendar as RC
from scripts import run_alpha_opportunity_model_v2 as CLI

ROOT = Path(__file__).resolve().parents[1]
V1_SEAL = "e3c699b197fd558506d7157fa6dd8cdb91156faccd0e6e9547d21d5baa23dd6e"
WORKFLOW = ROOT / ".github/workflows/alpha-opportunity-model-v2.yml"


@pytest.fixture
def spec():
    return S.read_json(S.DEFAULT_SPEC)


def seal():
    return S.DEFAULT_SPEC.with_suffix(".sha256").read_text().strip()


def small(spec, **inference):
    cfg = deepcopy(spec)
    cfg["inference"].update(replicates=20, **inference)
    return cfg


def fixture_root(tmp_path, spec, mutate=None):
    """A self-contained sealed copy: v1 provenance + registry + mutated v2 spec."""
    (tmp_path / "research_specs").mkdir()
    for name in ("alpha-opportunity-model-v1.json", "alpha-opportunity-model-v1.sha256",
                 "alpha-opportunity-model-v1-features.json"):
        (tmp_path / "research_specs" / name).write_bytes((ROOT / "research_specs" / name).read_bytes())
    value = deepcopy(spec)
    value["dependencyHashes"] = {}
    if mutate:
        mutate(value)
    path = tmp_path / "research_specs" / "alpha-opportunity-model-v2.json"
    path.write_bytes(V1S.canonical(value))
    path.with_suffix(".sha256").write_text(S.digest(value))
    return path, S.digest(value)


# --------------------------------------------------------------------------- #
# Versioning and immutability
# --------------------------------------------------------------------------- #
def test_v1_seal_untouched(spec):
    v1 = S.read_json(S.V1_SPEC)
    assert S.digest(v1) == V1_SEAL
    assert S.V1_SPEC.with_suffix(".sha256").read_text().strip() == V1_SEAL
    assert spec["supersedes"] == {**spec["supersedes"], "studyId": "alpha-opportunity-model-v1",
                                  "specSha256": V1_SEAL, "v1Executed": False}
    assert S.verify_v1_untouched(spec)
    v1_readiness = S.read_json(ROOT / "docs/results/alpha-opportunity-model-v1-readiness.json")
    assert v1_readiness["specSha256"] == V1_SEAL
    assert v1_readiness["verdict"] == "BLOCKED_PREREGISTRATION"


def test_v1_mutation_breaks_v2(tmp_path, spec):
    path, digest = fixture_root(tmp_path, spec)
    S.load_sealed(path, expected_hash=digest, root=tmp_path)
    v1 = S.read_json(tmp_path / "research_specs/alpha-opportunity-model-v1.json")
    v1["models"]["ridge"]["alpha"] = 11.0
    (tmp_path / "research_specs/alpha-opportunity-model-v1.json").write_bytes(V1S.canonical(v1))
    with pytest.raises(ValueError, match="V1_SEAL_CHANGED"):
        S.load_sealed(path, expected_hash=digest, root=tmp_path)


def test_v2_seal_is_deterministic_and_verified(spec):
    assert S.digest(spec) == seal() == S.digest(json.loads(S.DEFAULT_SPEC.read_text()))
    assert S.digest(spec) != V1_SEAL
    loaded, registry = S.load_sealed(expected_hash=seal())
    assert loaded == spec and registry["studyId"] == "alpha-opportunity-model-v1"
    assert spec["studyId"] == "alpha-opportunity-model-v2" and spec["immutableVersion"] == "2.0.0"


def test_mutated_spec_and_wrong_or_missing_seal(tmp_path, spec):
    path, digest = fixture_root(tmp_path, spec)
    with pytest.raises(ValueError, match="SEALED_SPEC_CHANGED"):
        S.load_sealed(path, expected_hash="0" * 64, root=tmp_path)
    with pytest.raises(ValueError, match="UNSEALED"):
        S.load_sealed(path, expected_hash="short", root=tmp_path)
    value = S.read_json(path)
    value["decisionContract"]["activeRule"] = "anything else"
    path.write_bytes(V1S.canonical(value))
    with pytest.raises(ValueError, match="SEALED_SPEC_CHANGED"):
        S.load_sealed(path, expected_hash=digest, root=tmp_path)
    path.with_suffix(".sha256").unlink()
    with pytest.raises(ValueError, match="UNSEALED"):
        S.load_sealed(path, expected_hash=digest, root=tmp_path)


def test_real_dependency_tampering_is_refused(tmp_path, spec):
    rel = "pipeline/alpha_opportunity_v2_decision.py"

    def mutate(value):
        value["dependencyHashes"] = {rel: spec["dependencyHashes"][rel]}
    path, digest = fixture_root(tmp_path, spec, mutate)
    (tmp_path / "pipeline").mkdir()
    (tmp_path / rel).write_text("# tampered\n")
    with pytest.raises(ValueError, match="SEALED_DEPENDENCY_CHANGED"):
        S.load_sealed(path, expected_hash=digest, root=tmp_path)


def test_v2_runner_never_substitutes_v1(spec):
    with pytest.raises(ValueError):
        S.load_sealed(S.V1_SPEC, expected_hash=V1_SEAL)
    with pytest.raises(ValueError):
        CLI.main(["--spec", str(S.V1_SPEC), "--sealed-sha256", V1_SEAL])


def test_dependency_closure_pins_the_execution_path(spec):
    deps = spec["dependencyHashes"]
    for rel in ("scripts/run_alpha_opportunity_model_v2.py", ".github/workflows/alpha-opportunity-model-v2.yml",
                "pipeline/alpha_opportunity_v2_decision.py", "pipeline/alpha_opportunity_v2_evaluation.py",
                "pipeline/alpha_opportunity_v2_model.py", "pipeline/alpha_opportunity_v2_spec.py",
                "pipeline/alpha_opportunity_features.py", "pipeline/alpha_opportunity_model.py",
                "research_specs/alpha-opportunity-model-v1.json", "requirements.txt",
                "docs/results/alpha-opportunity-model-v2-input-audit.json"):
        assert rel in deps
    for rel, sha in deps.items():
        assert V1S.file_hash(ROOT / rel) == sha, rel


# --------------------------------------------------------------------------- #
# The economic contract
# --------------------------------------------------------------------------- #
def test_benchmark_is_the_outside_option_with_zero_alpha(spec):
    assert D.OUTSIDE_OPTION_NET_ALPHA == 0.0
    contract = spec["decisionContract"]
    assert contract["outsideOption"]["expectedNetAlpha"] == 0.0
    assert contract["outsideOption"]["costCharged"] == 0.0
    # A stock exactly as good as its benchmark after cost does not move capital.
    assert D.classify(tradable=True, expected_net_alpha=0.0, probability=.5,
                      net_alpha_lower=0.0, probability_lower=.5) == D.BENCHMARK
    assert spec["benchmarks"] == {"US": "SPY", "KR": "069500.KS"}


def test_highest_ranked_negative_alpha_stock_is_not_an_opportunity():
    cost = .003
    gross = [-.02, -.01, -.004, .001, .0025]   # the best name still loses to the benchmark net
    decisions = []
    for i, mu in enumerate(gross):
        row = {"tradable": True, "grossExpectedAlpha": mu, "grossExpectedAlphaLower": mu - .01,
               "grossExpectedAlphaUpper": mu + .01, "probabilityNetOutperform": .45,
               "probabilityLower": .40}
        decisions.append((f"S{i}", D.decide(row, cost=cost)["opportunityClass"]))
    best = max(range(len(gross)), key=gross.__getitem__)
    assert decisions[best][1] == D.BENCHMARK
    result = D.opportunity_set(decisions)
    assert result == {"activeOpportunities": [], "count": 0, "state": "NO_ACTIVE_OPPORTUNITY"}


def test_number_of_active_names_is_endogenous():
    def row(mu, lower, p, pl):
        return {"tradable": True, "grossExpectedAlpha": mu, "grossExpectedAlphaLower": lower,
                "grossExpectedAlphaUpper": mu + .01, "probabilityNetOutperform": p, "probabilityLower": pl}
    cross_sections = {
        "none": [row(-.01, -.02, .4, .3)] * 12,
        "one": [row(.03, .02, .7, .6)] + [row(-.01, -.02, .4, .3)] * 11,
        "seven": [row(.03, .02, .7, .6)] * 7 + [row(.01, -.01, .55, .45)] * 5,
    }
    counts = {}
    for key, rows in cross_sections.items():
        decisions = [(f"{key}{i}", D.decide(r, cost=.003)["opportunityClass"]) for i, r in enumerate(rows)]
        counts[key] = D.opportunity_set(decisions)["count"]
    assert counts == {"none": 0, "one": 1, "seven": 7}


def test_no_arbitrary_minimum_alpha_hurdle(spec):
    # A tiny positive net edge the model can distinguish from zero IS an opportunity.
    assert D.classify(tradable=True, expected_net_alpha=1e-6, probability=.500001,
                      net_alpha_lower=5e-7, probability_lower=.5000005) == D.ACTIVE
    contract = spec["decisionContract"]
    assert contract["minimumAlphaHurdle"] is None
    assert contract["probabilityCutoffOtherThanIndifference"] is None
    assert D.PROBABILITY_INDIFFERENCE == 0.5
    for bad in ("minimumEdge", "minimumAlphaHurdle", "concentrationRiskMultiple"):
        assert bad in S.FORBIDDEN_DECISION_PARAMETERS


@pytest.mark.parametrize("key,path", [("minimumEdge", ("investability",)),
                                      ("regionQuota", ("decisionContract",)),
                                      ("fixedTopN", ("decisionContract",)),
                                      ("portfolioValue", ("smallCapitalAssumption",)),
                                      ("tradeNotional", ("tradabilityGuard",))])
def test_spec_reintroducing_a_removed_parameter_is_refused(tmp_path, spec, key, path):
    def mutate(value):
        target = value
        for part in path:
            target = target.setdefault(part, {})
        target[key] = 0.02
    p, digest = fixture_root(tmp_path, spec, mutate)
    with pytest.raises(ValueError, match="FORBIDDEN_DECISION_PARAMETER"):
        S.load_sealed(p, expected_hash=digest, root=tmp_path)


def test_no_fixed_region_quota_or_holdings(spec):
    contract = spec["decisionContract"]
    for key in ("fixedTopN", "fixedHoldings", "regionQuota", "investedFraction"):
        assert contract[key] is None
    # A KR-only (or US-only) active set is a valid outcome; nothing balances it.
    assert D.opportunity_set([("005930.KS", D.ACTIVE), ("AAPL", D.BENCHMARK)])["count"] == 1


def test_no_user_portfolio_value_or_order_size_required(spec):
    text = (ROOT / "scripts/run_alpha_opportunity_model_v2.py").read_text()
    for flag in ("portfolio-value", "notional", "capital", "adv"):
        assert f"--{flag}" not in text
    assert spec["smallCapitalAssumption"]["id"] == "SMALL_CAPITAL_ASSUMPTION"
    assert spec["tradabilityGuard"]["advRequiredForAlphaResearch"] is False
    assert "advSnapshotSha256" not in json.dumps(spec["tradabilityGuard"])
    assert spec["decisionContract"]["portfolioValue"] is None
    assert spec["decisionContract"]["orderNotional"] is None


def test_transaction_cost_enters_net_alpha(spec):
    us = D.dated_round_trip_cost("US", "2020-01-01", spec)
    kr_2013, kr_2025 = (D.dated_round_trip_cost("KR", d, spec) for d in ("2013-01-01", "2025-01-01"))
    assert us == pytest.approx(.00163) and kr_2013 == pytest.approx(.0041) and kr_2025 == pytest.approx(.0026)
    # Positive gross alpha smaller than the cost is not an opportunity.
    row = {"tradable": True, "grossExpectedAlpha": .003, "grossExpectedAlphaLower": .0028,
           "grossExpectedAlphaUpper": .0032, "probabilityNetOutperform": .45, "probabilityLower": .44}
    decided = D.decide(row, cost=kr_2013)
    assert decided["expectedNetAlpha"] == pytest.approx(.003 - .0041)
    assert decided["opportunityClass"] == D.BENCHMARK
    assert E.net_label(.004, .0041) == 0 and E.net_label(.0042, .0041) == 1
    assert D.net_alpha(.01, -1) is None and D.net_alpha(np.nan, .001) is None


def test_expected_alpha_probability_and_uncertainty_stay_distinct():
    base = dict(tradable=True, expected_net_alpha=.02, probability=.6, net_alpha_lower=.01, probability_lower=.55)
    assert D.classify(**base) == D.ACTIVE
    # Mean favours, probability does not (right-skewed payoff): benchmark retained.
    assert D.classify(**{**base, "probability": .45}) == D.DISAGREE
    assert D.classify(**{**base, "expected_net_alpha": -.01}) == D.DISAGREE
    # Large point estimate the model cannot distinguish from the benchmark.
    assert D.classify(**{**base, "net_alpha_lower": -.03}) == D.UNRESOLVED
    assert D.classify(**{**base, "probability_lower": .49}) == D.UNRESOLVED
    assert D.classify(**{**base, "net_alpha_lower": np.nan}) == D.UNMEASURED
    assert D.classify(**{**base, "tradable": False}) == D.NOT_TRADABLE
    assert D.ACTIVE_CLASSES == frozenset({D.ACTIVE})


def test_signal_layer_carries_no_portfolio_fields(spec):
    row = {"tradable": True, "grossExpectedAlpha": .02, "grossExpectedAlphaLower": .01,
           "grossExpectedAlphaUpper": .03, "probabilityNetOutperform": .6, "probabilityLower": .55}
    assert not D.PORTFOLIO_FIELDS & D.decide(row, cost=.002).keys()
    for name in ("alpha_opportunity_v2_decision", "alpha_opportunity_v2_evaluation",
                 "alpha_opportunity_v2_model", "alpha_opportunity_v2_spec"):
        tree = ast.parse((ROOT / "pipeline" / f"{name}.py").read_text())
        used = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        used |= {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        imported = {a.name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
        modules = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
        assert not {"select_portfolio_by_scores", "baseline_weights", "kelly_fraction"} & used, name
        assert not {"kelly_portfolio", "replay_valuation", "selection_null"} & (imported | modules), name
    report = {k: None for k in spec["expectedOutputSchema"]["resultRequired"]}
    report.update(studyId=S.STUDY, specSha256=S.digest(spec), promotionEligible=False)
    S.validate_result(report, None, spec)
    for field in ("weights", "positions", "NAV", "CAGR"):
        with pytest.raises(ValueError, match="PORTFOLIO_OUTPUT"):
            S.validate_result({**report, field: []}, None, spec)
    with pytest.raises(ValueError, match="PROMOTION"):
        S.validate_result({**report, "promotionEligible": True}, None, spec)


def _closure(start):
    seen, stack = set(), list(start)
    while stack:
        m = stack.pop()
        p = ROOT / "pipeline" / (m + ".py")
        if m in seen or not p.exists():
            continue
        seen.add(m)
        for node in ast.walk(ast.parse(p.read_text())):
            if isinstance(node, ast.ImportFrom) and node.level == 1:
                stack.extend([node.module.split(".")[0]] if node.module else [a.name for a in node.names])
            elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith("pipeline"):
                parts = node.module.split(".")
                stack.extend([parts[1]] if len(parts) > 1 else [a.name for a in node.names])
    return seen


def test_guru_and_13f_modules_are_not_imported(spec):
    used = _closure(["alpha_opportunity_v2_spec", "alpha_opportunity_v2_decision",
                     "alpha_opportunity_v2_evaluation", "alpha_opportunity_v2_model",
                     "alpha_opportunity_features", "regional_alpha_features"])
    runner = ast.parse((ROOT / "scripts/run_alpha_opportunity_model_v2.py").read_text())
    runner_imports = {a.name for n in ast.walk(runner) if isinstance(n, ast.ImportFrom) for a in n.names}
    for guru in ("guru_13f_store", "institutional_13f", "security_identity", "expert_consensus",
                 "national_pension", "sec_access"):
        assert guru not in used and guru not in runner_imports
        assert f"pipeline/{guru}.py" not in spec["dependencyHashes"]
    assert "GURU_13F" in spec["excludedFamilies"]
    features = json.dumps(spec["allowedFeatures"])
    assert "13f" not in features.lower() and "guru" not in features.lower()


def test_no_production_module_imports_v2():
    for path in (ROOT / "pipeline").glob("*.py"):
        if path.stem.startswith("alpha_opportunity_"):
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in node.names] + [getattr(node, "module", "") or ""]
                assert not any("alpha_opportunity" in n for n in names), path


# --------------------------------------------------------------------------- #
# PIT guards
# --------------------------------------------------------------------------- #
def test_tradability_guard_is_pit_and_size_free():
    ok, reason = D.tradability([10.] * 20, [100.] * 20, window=20)
    assert ok and reason == "TRADABLE"
    assert D.tradability([10.] * 19, [100.] * 19, window=20)[1] == "INSUFFICIENT_TRADING_HISTORY"
    halted = [100.] * 20
    halted[5] = 0.
    assert D.tradability([10.] * 20, halted, window=20) == (False, "ZERO_OR_MISSING_VOLUME_IN_WINDOW")
    gap = [10.] * 20
    gap[3] = np.nan
    assert D.tradability(gap, [100.] * 20, window=20) == (False, "MISSING_OR_NONPOSITIVE_CLOSE_IN_WINDOW")
    assert D.tradability([10.] * 19 + [np.nan], [100.] * 20, window=20) == (False, "NO_SIGNAL_DATE_PRICE")


def test_runner_tradability_never_reads_after_signal_date():
    days = RC.sessions("2020-01-01", "2020-06-30", "US")
    panel = pd.DataFrame({"Close": 10., "Volume": 100.}, index=days)
    date = str(days[60].date())
    frame = pd.DataFrame({"date": [date], "ticker": ["SYN"], "region": ["US"]})
    a = CLI.tradability_frame({"SYN": panel}, frame, "US", 20)
    later = panel.copy()
    later.loc[later.index > date, ["Close", "Volume"]] = np.nan
    b = CLI.tradability_frame({"SYN": later}, frame, "US", 20)
    assert a.tradable.tolist() == b.tradable.tolist() == [True]
    early = panel.copy()
    early.iloc[50, 1] = 0.
    assert CLI.tradability_frame({"SYN": early}, frame, "US", 20).tradable.tolist() == [False]
    missing = CLI.tradability_frame({}, frame, "US", 20)
    assert missing.tradabilityReason.tolist() == ["NO_SEALED_PRICE_PANEL"] and not missing.vouched.any()


def test_v2_labels_equal_v1_target_semantics():
    days = RC.sessions("2020-07-01", "2021-03-01", "US")
    bench = pd.DataFrame({"Close": 100. + np.arange(len(days)) * .1}, index=days)
    stock = pd.DataFrame({"Close": 100. + np.arange(len(days))}, index=days)
    prices = {"SYNTHETIC": stock, "SPY": bench}
    sessions = RC.sessions("2012-01-01", "2027-12-31", "US")
    for date in ("2020-07-02", "2020-09-04", "2020-11-25"):
        for horizon, through in ((21, "2021-03-01"), (126, "2020-12-01")):
            v1 = F.target_at(prices, "US", "SYNTHETIC", date, horizon, through)
            v2 = E.target_from_sessions(sessions, prices, "SPY", "SYNTHETIC", date, horizon, through)
            assert v2["entryDate"] == v1["entryDate"] and v2["outcomeEndDate"] == v1["outcomeEndDate"]
            assert v2["labelStatus"] == v1["labelStatus"]
            assert v2["forwardRelativeReturn"] == v1["forwardRelativeReturn"]
    exit_ = E.target_from_sessions(sessions, prices, "SPY", "SYNTHETIC", "2020-07-02", 21, "2021-03-01")["outcomeEndDate"]
    prices["SYNTHETIC"] = stock.drop(pd.Timestamp(exit_))
    got = E.target_from_sessions(sessions, prices, "SPY", "SYNTHETIC", "2020-07-02", 21, "2021-03-01")
    assert got["labelStatus"] == E.UNRESOLVED and got["forwardRelativeReturn"] is None


def test_membership_and_filings_stay_strictly_earlier():
    from pipeline.regional_alpha_features import MembershipSnapshots
    snaps = MembershipSnapshots([{"date": "2020-01-03", "members": ["A"]},
                                 {"date": "2020-01-10", "members": ["B"]}])
    assert snaps.on("2020-01-10")["members"] == ["A"]
    rows = [{"id": "a", "availableFrom": "2020-01-10"}]
    assert F.visible_filings(rows, "2020-01-10", "US") == []


# --------------------------------------------------------------------------- #
# Survivorship and evaluation mechanics
# --------------------------------------------------------------------------- #
def test_survivorship_treatments_and_tolerance(spec):
    n = 20
    group = pd.DataFrame({"forwardRelativeReturn": np.linspace(-.1, .1, n), "beatBenchmarkNet": 1,
                          "labelStatus": E.MATURED})
    group.loc[:1, ["forwardRelativeReturn", "labelStatus"]] = [None, E.UNRESOLVED]
    observed, status = E.apply_treatment(group, "OBSERVED_ONLY", spec)
    assert status == "MEASURED" and len(observed) == n - 2
    worst, status = E.apply_treatment(group, "WORST_PLAUSIBLE", spec)
    tail = np.quantile(group.forwardRelativeReturn.dropna(), .05)
    assert worst.loc[:1, "forwardRelativeReturn"].tolist() == [tail, tail]
    assert worst.loc[:1, "beatBenchmarkNet"].tolist() == [0, 0]
    group.loc[:4, ["forwardRelativeReturn", "labelStatus"]] = [None, E.UNRESOLVED]   # 25% > 20%
    assert E.apply_treatment(group, "OBSERVED_ONLY", spec)[1] == "INCOMPLETE_UNRESOLVED_ENDPOINTS"
    assert spec["survivorship"]["regionYearUnvouchedTolerancePct"] == pit_data.HISTORICAL_UNIVERSE_GAP_TOLERANCE_PCT


def test_region_year_eligibility_uses_repository_tolerance(spec):
    frame = pd.DataFrame({"region": "US", "date": ["2016-01-08"] * 10 + ["2017-01-06"] * 10,
                          "vouched": [True] * 7 + [False] * 3 + [True] * 9 + [False]})
    table = {(e["year"]): e for e in CLI.eligibility(frame, spec)}
    assert not table["2016"]["eligible"] and table["2016"]["unvouchedPct"] == pytest.approx(30)
    assert table["2017"]["eligible"]


def test_input_audit_is_input_only_and_matches_spec(spec):
    audit = S.read_json(ROOT / "docs/results/alpha-opportunity-model-v2-input-audit.json")
    assert audit["historicalOutcomesComputed"] is False and audit["returnsComputed"] is False
    assert audit["priceValuesRead"] is False
    assert audit["usYearsExcludedByLowerBound"] == ["2013", "2014", "2015", "2016"]
    assert audit["repositoryTolerancePct"] == spec["survivorship"]["regionYearUnvouchedTolerancePct"]
    assert audit["usNoPanelNames"] == 194 and audit["usMembershipUnion"] == 829


def test_calendar_depth_is_outcome_free_and_serialisable(spec):
    counts = pd.Series(["2016"] * 52 + ["2017"] * 52 + ["2018"] * 52 + ["2019"] * 52 + ["2020"] * 10).value_counts()
    depth = E.calendar_depth(counts.to_dict(), spec)
    assert depth == {"evaluationYearsUpperBound": 5, "evaluationDatesUpperBound": 218,
                     "status": "SUFFICIENT_UPPER_BOUND"}
    V1S.canonical(depth)
    assert E.calendar_depth({"2016": 52, "2017": 52}, spec)["status"] == "BLOCKED_BY_SAMPLE_DEPTH"


def test_absolute_slope_is_the_pooled_date_balanced_regression():
    rng = np.random.default_rng(1)
    frames = []
    for d in range(30):
        n = 5 + d % 4
        mu = rng.normal(d * .001, .01, n)
        frames.append(pd.DataFrame({"date": d, "mu": mu, "y": .5 * mu + rng.normal(0, .005, n)}))
    data = pd.concat(frames)
    table = pd.DataFrame([{"sMu": g.mu.mean(), "sY": g.y.mean(), "sMu2": (g.mu ** 2).mean(),
                           "sMuY": (g.mu * g.y).mean()} for _, g in data.groupby("date")])
    w = V1M.date_weights(data.date)
    mbar, ybar = np.average(data.mu, weights=w), np.average(data.y, weights=w)
    expected = np.average((data.mu - mbar) * (data.y - ybar), weights=w) / np.average((data.mu - mbar) ** 2, weights=w)
    assert E.absolute_slope(table) == pytest.approx(expected)


def _opp_table(n, active_every=1, level=.01, spread=.01):
    rows = []
    for i, d in enumerate(pd.date_range("2016-01-01", periods=n, freq="W-FRI").strftime("%Y-%m-%d")):
        active = i % active_every == 0
        rows.append({"date": d, "state": "ACTIVE_OPPORTUNITIES" if active else "NO_ACTIVE_OPPORTUNITY",
                     "activeNet": level if active else np.nan,
                     "spreadOverNonActive": spread if active else np.nan,
                     "stressedActiveNet": level * .9 if active else np.nan,
                     "activeNetCostX2": level - .001 if active else np.nan})
    return pd.DataFrame(rows)


def test_zero_active_opportunities_is_a_valid_outcome(spec):
    cfg = small(spec)
    none = _opp_table(200, active_every=10 ** 9)
    none.loc[0, ["state", "activeNet", "spreadOverNonActive", "stressedActiveNet"]] = ["NO_ACTIVE_OPPORTUNITY", np.nan, np.nan, np.nan]
    result = E.opportunity_evidence(none, cfg)
    assert result["evidence"] is False and result["activeDates"] == 0
    assert result["noActiveOpportunityDates"] == 200 and result["reason"] == "TOO_FEW_ACTIVE_OPPORTUNITY_DATES"
    group = pd.DataFrame({"forwardRelativeReturn": np.linspace(-.05, .05, 12), "roundTripCost": .002,
                          "activeOpportunity": False})
    row = E.opportunity_date(group, unvouched_share=.1, spec=spec)
    assert row["state"] == "NO_ACTIVE_OPPORTUNITY" and np.isnan(row["activeNet"])


def test_opportunity_needs_level_spread_stress_and_both_halves(spec):
    cfg = small(spec)
    assert E.opportunity_evidence(_opp_table(200), cfg)["evidence"] is True
    carry = _opp_table(200, spread=-.002)     # beats 0 only through universe carry
    assert E.opportunity_evidence(carry, cfg)["evidence"] is False
    late = _opp_table(200)
    late.loc[:99, "activeNet"] = -.01          # first half negative
    assert E.opportunity_evidence(late, cfg)["halvesPositive"] is False
    sparse = _opp_table(200, active_every=5)   # 40 active dates < 52
    assert E.opportunity_evidence(sparse, cfg)["reason"] == "TOO_FEW_ACTIVE_OPPORTUNITY_DATES"
    assert "activeNetCostX2" in E.opportunity_evidence(_opp_table(200), cfg)["costStressDisclosureNotGated"]


def test_stressed_level_uses_date_worst_plausible(spec):
    group = pd.DataFrame({"forwardRelativeReturn": np.linspace(-.1, .1, 20), "roundTripCost": .002,
                          "activeOpportunity": [True] * 2 + [False] * 18})
    row = E.opportunity_date(group, unvouched_share=.2, spec=spec)
    active_net = float((group.forwardRelativeReturn - .002)[:2].mean())
    tail = np.quantile(group.forwardRelativeReturn, .05)
    assert row["stressedActiveNet"] == pytest.approx(.8 * active_net + .2 * (tail - .002))


def _ece_null(n, dates=300, seed=42):
    rng = np.random.default_rng(seed)
    rows = []
    for d in range(dates):
        p = rng.uniform(.3, .7, n)
        z = (rng.uniform(size=n) < p).astype(int)
        frame = pd.DataFrame({"forwardRelativeReturn": z - .5, "beatBenchmarkNet": z,
                              "probabilityNetOutperform": p, "grossExpectedAlpha": p - .5,
                              "trainingBaseRate": .5, "trainingMeanReturn": 0.})
        rows.append({"date": d, **E.date_summary(frame)})
    return pd.DataFrame(rows)


def test_ece_gate_is_calibrated_against_a_simulated_null(spec):
    """v1's per-date ECE rejects a PERFECTLY calibrated 120-name model; pooled does not."""
    recorded = spec["evaluation"]["C_probabilityCalibration"]["eceNull"]
    for n in (120, 500):
        table = _ece_null(n)
        assert table.perDateEce.mean() == pytest.approx(recorded["perDateMeanEce"][str(n)], abs=1e-4)
        assert E.pooled_ece(table) == pytest.approx(recorded["pooledEce"][str(n)], abs=1e-4)
        assert E.pooled_ece(table) < spec["evidenceGates"]["maxEce"]
    assert _ece_null(120).perDateEce.mean() > spec["evidenceGates"]["maxEce"]


def _measured(quality=True, stable=True):
    return {"status": "MEASURED", "quality": quality, "stable": stable}


@pytest.mark.parametrize("pred,opp,expected", [
    ((_measured(), _measured()), (True, True), "OPPORTUNITY_EVIDENCE"),
    ((_measured(), _measured()), (True, False), "PREDICTIVE_EVIDENCE_BENCHMARK_PREFERRED"),
    ((_measured(), _measured(quality=False)), (True, True), "NO_MODEL_EVIDENCE"),
    ((_measured(stable=False), _measured()), (True, True), "MODEL_UNSTABLE"),
    ((_measured(), {"status": "DATA_INSUFFICIENT"}), (True, True), "DATA_INSUFFICIENT"),
    ((_measured(), _measured()), (None, True), "DATA_INSUFFICIENT"),
])
def test_verdict_is_conjunctive_across_treatments(pred, opp, expected):
    per = {t: {"predictive": p, "opportunity": {"evidence": o}}
           for t, p, o in zip(E.TREATMENTS, pred, opp)}
    assert E.verdict(per)["verdict"] == expected
    assert E.verdict(per, pit_valid=False)["verdict"] == "PIT_INVALID"
    assert E.verdict(per, numerically_stable=False)["verdict"] == "MODEL_UNSTABLE"
    assert E.verdict(per)["promotionEligible"] is False


def test_uncertainty_bootstrap_equals_v1_statistic(spec):
    rng = np.random.default_rng(42)
    dates = pd.date_range("2013-01-04", periods=40, freq="W-FRI").strftime("%Y-%m-%d")
    x = rng.normal(size=len(dates) * 6)
    data = pd.DataFrame({"date": np.repeat(dates, 6), "region": "US", "x": x,
                         "forwardRelativeReturn": .01 * x + rng.normal(0, .005, len(x)),
                         "beatBenchmarkNet": (x > .2).astype(int)})
    train, valid = data.iloc[:180], data.iloc[180:]
    cfg = deepcopy(spec)
    cfg["uncertainty"].update(replicates=4, blockDates=5, minimumTrainingBlocks=2)
    ours = M.prediction_uncertainty(train, valid, ["x"], cfg)
    theirs = V1M.prediction_uncertainty(M.as_v1_target(train), valid, ["x"], cfg)
    for key in ("probabilityLower", "probabilityUpper", "meanLower", "meanUpper"):
        np.testing.assert_allclose(ours[key], theirs[key], rtol=0, atol=1e-12)


def _synthetic_cell(n_dates=330, names=14, seed=7):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2016-01-08", periods=n_dates, freq="W-FRI")
    rows = []
    for d in dates:
        signal = rng.normal(size=names)
        rel = .02 * signal + rng.normal(0, .02, names)
        end = d + pd.Timedelta(days=30)
        for i in range(names):
            rows.append({"date": d.strftime("%Y-%m-%d"), "outcomeEndDate": end.strftime("%Y-%m-%d"),
                         "ticker": f"SYN{i}", "region": "US", "tradable": True, "relative126": signal[i],
                         "forwardRelativeReturn": rel[i], "labelStatus": E.MATURED, "roundTripCost": .00163})
    data = pd.DataFrame(rows)
    data["beatBenchmarkNet"] = (data.forwardRelativeReturn > data.roundTripCost).astype(int)
    for col in ("acceleration21", "vol63", "logVolumeShock60", "shockPersistence5d", "volumePriceAlignment"):
        data[col] = rng.normal(size=len(data))
    return data


def test_synthetic_end_to_end_cell_runs_without_real_data(spec):
    """Exercise predict_cell + evaluate_cell on synthetic data with tiny resampling."""
    cfg = deepcopy(spec)
    cfg["walkForward"].update(featureStart="2016-01-01", minimumHistoryMonths=12, minimumMaturedDates=40)
    cfg["uncertainty"].update(replicates=3, blockDates=5, minimumTrainingBlocks=2)
    cfg["inference"].update(replicates=10, blockDates=5, minimumEvaluationBlocks=4)
    cfg["evidenceGates"].update(minimumEvaluationFolds=3, minimumActiveDates=5)
    cfg["dataCutoff"] = "2030-01-01"
    data = _synthetic_cell()
    preds, folds, failures = M.predict_cell(data, sorted(data.date.unique()), "US", 21, cfg, "SYNTHETIC")
    assert preds and not failures
    combined = pd.concat(preds, ignore_index=True)
    linear = combined.loc[combined.family.eq("LINEAR")]
    assert set(linear.opportunityClass) <= set(D.CLASSES)
    assert combined.loc[combined.family.eq("SHALLOW_CHALLENGER"), "activeOpportunity"].isna().all()
    assert not {"weight", "weights", "position", "rank"} & set(combined.columns)
    unvouched = {("US", d): .05 for d in linear.date.unique()}
    result = E.evaluate_cell(linear, folds, failures, unvouched, cfg, region="US", horizon=21)
    assert result["verdict"] in E.PRIORITY and result["promotionEligible"] is False
    # A strong synthetic signal reaches every gate (this is plumbing, not evidence).
    assert result["verdict"] == "OPPORTUNITY_EVIDENCE"
    assert set(result["evidence"]) == set(E.TREATMENTS)
    V1S.canonical({k: v for k, v in result.items()})


# --------------------------------------------------------------------------- #
# Preregistration cannot compute outcomes; workflow refuses a wrong seal
# --------------------------------------------------------------------------- #
def test_status_is_ready_and_artifacts_record_no_outcomes(spec):
    assert S.preregistration_status(spec) == S.READY
    report = S.readiness(spec, seal())
    assert report["preregistrationStatus"] in S.STATUSES
    assert report["historicalOutcomesComputed"] is False and report["historicalModelsTrained"] is False
    assert S.read_json(ROOT / "docs/results/alpha-opportunity-model-v2-readiness.json") == report
    artifacts = {p.name for p in (ROOT / "docs/results").glob("alpha-opportunity-model-v2-*")}
    assert artifacts == {"alpha-opportunity-model-v2-input-audit.json", "alpha-opportunity-model-v2-readiness.json"}


def test_status_derives_from_real_blockers(spec):
    for category in S.BLOCKER_PRECEDENCE:
        value = deepcopy(spec)
        value["designBlockers"] = [{"id": "X", "category": category}]
        value["preregistrationStatus"] = category
        assert S.preregistration_status(value) == category
        with pytest.raises(ValueError, match=category):
            S.require_execution(value, reviewed=True, branch="refs/heads/main", prerequisites={"ok": True})
    value = deepcopy(spec)
    value["designBlockers"] = [{"id": "X", "category": "BLOCKED_BY_SAMPLE_DEPTH"}]
    with pytest.raises(ValueError, match="DISAGREES"):
        S.preregistration_status(value)
    value["designBlockers"] = [{"id": "X", "category": "BLOCKED_PREREGISTRATION"}]
    with pytest.raises(ValueError, match="UNREGISTERED"):
        S.preregistration_status(value)


def test_cli_readiness_only_never_executes(monkeypatch, capsys):
    monkeypatch.setattr(CLI, "execute", lambda *a: pytest.fail("must not execute"))
    monkeypatch.setattr(CLI, "verify_inputs", lambda *a: pytest.fail("must not read inputs"))
    assert CLI.main(["--sealed-sha256", seal()]) == 0
    first = capsys.readouterr().out
    CLI.main(["--sealed-sha256", seal()])
    assert capsys.readouterr().out == first
    assert json.loads(first)["historicalOutcomesComputed"] is False


def test_execution_refused_off_main_or_unreviewed(monkeypatch, tmp_path):
    monkeypatch.setattr(CLI, "execute", lambda *a: pytest.fail("must not execute"))
    monkeypatch.setattr(CLI, "verify_inputs", lambda *a: pytest.fail("must not read inputs"))
    args = ["--sealed-sha256", seal(), "--execute", "--input-root", str(tmp_path),
            "--us-membership", str(tmp_path / "m"), "--output", str(tmp_path / "out")]
    monkeypatch.setenv("GITHUB_REF", "refs/heads/claude/branch")
    with pytest.raises(ValueError, match="MERGE_AND_REVIEW"):
        CLI.main(args + ["--reviewed"])
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    with pytest.raises(ValueError, match="MERGE_AND_REVIEW"):
        CLI.main(args)
    with pytest.raises(ValueError, match="SEALED_SPEC_CHANGED"):
        CLI.main(["--sealed-sha256", "f" * 64, "--execute", "--reviewed"])
    assert not (tmp_path / "out").exists()


def test_pre_label_gate_stops_before_any_label(monkeypatch, tmp_path, spec):
    """A coverage failure must stop the run before target construction."""
    from pipeline import regional_alpha_features as sources
    days = RC.sessions("2015-06-01", "2020-12-31", "US")
    dates = [str(d.date()) for d in days[days.dayofweek == 4]][30:]
    frame = pd.DataFrame([{"date": d, "region": r, "ticker": f"{r}{i}", "benchmark": "SPY"}
                          for d in dates for r in ("US", "KR") for i in range(12)])
    panel = pd.DataFrame({"Close": 10., "Volume": 100.}, index=RC.sessions("2012-01-01", "2020-12-31", "US"))
    kr_panel = pd.DataFrame({"Close": 10., "Volume": 100.}, index=RC.sessions("2012-01-01", "2020-12-31", "KR"))
    prices = {f"US{i}": panel for i in range(12)} | {f"KR{i}": kr_panel for i in range(12)}
    monkeypatch.setattr(sources, "load_inputs", lambda *_: ({"sha256": spec["snapshots"]["replayManifestSha256"]}, prices, None, None))
    monkeypatch.setattr(sources, "load_memberships", lambda *_: {})
    monkeypatch.setattr(S, "file_hash", lambda *_: spec["snapshots"]["usMembershipSha256"])
    monkeypatch.setattr(F, "load_raw", lambda *_: ({}, {}))
    monkeypatch.setattr(F, "build_matrix", lambda *a, **k: frame.copy())   # every feature missing
    monkeypatch.setattr(E, "target_from_sessions", lambda *a, **k: pytest.fail("label built before gates"))
    registry = S.read_json(ROOT / spec["featureRegistry"])
    report = CLI.execute(spec, registry, tmp_path / "in", tmp_path / "m.gz", tmp_path.parent / (tmp_path.name + "-out"))
    assert report["stoppedBeforeLabels"] is True
    assert report["status"] == "BLOCKED_BY_DATA_INTEGRITY"
    assert report["results"] == [] and report["promotionEligible"] is False


def test_workflow_is_manual_main_only_and_validates_v2_seal_first():
    text = WORKFLOW.read_text()
    assert "workflow_dispatch:" in text
    for trigger in ("schedule:", "push:", "pull_request:", "workflow_run:"):
        assert trigger not in text
    assert "contents: write" not in text and "contents: read" in text
    assert "if: github.ref == 'refs/heads/main'" in text
    assert "run_alpha_opportunity_model_v2.py" in text
    assert "run_alpha_opportunity_model.py " not in text and "alpha_opportunity_spec import" not in text
    guard = text.index("alpha_opportunity_v2_spec import load_sealed, require_execution")
    assert guard < text.index("pip install") < text.index("--execute")
    assert "upload-artifact" in text and "git push" not in text
    assert "--sealed-sha256 \"$REVIEWED_SEAL\"" in text
