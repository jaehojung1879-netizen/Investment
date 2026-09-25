"""alpha-opportunity-model-v3 contract tests. Synthetic fixtures and sealed
identities only: no real price level, label, return or model fit is read here.
"""
from __future__ import annotations

import ast
from copy import deepcopy
import json
from pathlib import Path
import shutil

import pytest

from pipeline import alpha_opportunity_spec as V1S
from pipeline import alpha_opportunity_v3_decision as D
from pipeline import alpha_opportunity_v3_spec as S
from pipeline import alpha_opportunity_v3_survivorship as A
from pipeline import portfolio_validation as PV
from pipeline import regional_alpha_features as RAF
from pipeline import replay_calendar as RC
from scripts import run_alpha_opportunity_model_v3 as CLI

ROOT = Path(__file__).resolve().parents[1]
V1_SEAL = "e3c699b197fd558506d7157fa6dd8cdb91156faccd0e6e9547d21d5baa23dd6e"
V2_SEAL = "97c3727b37eeab71e31ffee17a2f81cac29f0333552ff04a5374ef48484b0e19"
AUDIT = ROOT / "docs/results/alpha-opportunity-model-v3-survivorship-audit.json"


@pytest.fixture
def spec():
    return S.read_json(S.DEFAULT_SPEC)


def seal():
    return S.DEFAULT_SPEC.with_suffix(".sha256").read_text().strip()


def row(**kw):
    base = {"tradable": True, "grossExpectedAlpha": .02, "grossExpectedAlphaLower": .01,
            "grossExpectedAlphaUpper": .03, "probabilityNetOutperform": .6,
            "probabilityLower": .55, "probabilityUpper": .65, "predictiveResidualRms": .09}
    return {**base, **kw}


def sealed_copy(tmp_path, spec, extra=()):
    """Copy exactly the sealed files (+extras) into an isolated root."""
    for rel in list(spec["dependencyHashes"]) + ["research_specs/alpha-opportunity-model-v3.json",
                                                 "research_specs/alpha-opportunity-model-v3.sha256", *extra]:
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, dst)
    return tmp_path / "research_specs/alpha-opportunity-model-v3.json"


# --------------------------------------------------------------------------- #
# 1-3 Versioning
# --------------------------------------------------------------------------- #
def test_v1_and_v2_seals_unchanged(spec):
    for study, sha in (("alpha-opportunity-model-v1", V1_SEAL), ("alpha-opportunity-model-v2", V2_SEAL)):
        path = ROOT / "research_specs" / f"{study}.json"
        assert S.digest(S.read_json(path)) == sha == path.with_suffix(".sha256").read_text().strip()
    assert {p["studyId"]: p["specSha256"] for p in spec["priorVersions"]} == {
        "alpha-opportunity-model-v1": V1_SEAL, "alpha-opportunity-model-v2": V2_SEAL}
    assert S.verify_prior_versions(spec)


def test_prior_version_mutation_breaks_v3(tmp_path, spec):
    path = sealed_copy(tmp_path, spec)
    S.load_sealed(path, expected_hash=seal(), root=tmp_path)
    v2 = S.read_json(tmp_path / "research_specs/alpha-opportunity-model-v2.json")
    v2["models"]["ridge"]["alpha"] = 11.0
    (tmp_path / "research_specs/alpha-opportunity-model-v2.json").write_bytes(V1S.canonical(v2))
    with pytest.raises(ValueError, match="SEALED_DEPENDENCY_CHANGED|PRIOR_SEAL_CHANGED"):
        S.load_sealed(path, expected_hash=seal(), root=tmp_path)


def test_v3_seal_deterministic_and_verified(spec):
    assert S.digest(spec) == seal() == S.digest(json.loads(S.DEFAULT_SPEC.read_text()))
    assert S.load_sealed(expected_hash=seal()) == spec
    with pytest.raises(ValueError, match="SEALED_SPEC_CHANGED"):
        S.load_sealed(expected_hash="0" * 64)
    with pytest.raises(ValueError):
        S.load_sealed(ROOT / "research_specs/alpha-opportunity-model-v2.json", expected_hash=V2_SEAL)


# --------------------------------------------------------------------------- #
# 4-19 Economic contract
# --------------------------------------------------------------------------- #
def test_benchmark_outside_option_is_zero(spec):
    assert D.OUTSIDE_OPTION_NET_ALPHA == 0.0
    assert spec["decisionContract"]["outsideOption"]["expectedNetAlpha"] == 0.0
    assert spec["decisionContract"]["alphaExistenceRule"] == "expectedNetAlpha > 0"
    assert D.describe(row(grossExpectedAlpha=.002), cost=.002)["expectedValueClass"] == D.BENCHMARK


def test_positive_ev_with_probability_below_half_is_still_positive():
    rec = D.describe(row(probabilityNetOutperform=.40, probabilityLower=.35), cost=.002)
    assert rec["expectedValueClass"] == D.POSITIVE and rec["positiveExpectedAlpha"]
    assert rec["distributionState"] == D.EV_POSITIVE_PROB_NOT_ABOVE_HALF
    assert rec["probabilityNetOutperform"] == .40


def test_positive_ev_with_lower_bound_below_zero_is_still_positive():
    rec = D.describe(row(grossExpectedAlphaLower=-.03), cost=.002)
    assert rec["expectedValueClass"] == D.POSITIVE
    assert rec["fittedUncertaintyState"] == D.FITTED_INTERVAL_SPANS_ZERO
    assert rec["expectedNetAlphaLower"] == pytest.approx(-.032)


def test_non_positive_ev_prefers_benchmark_whatever_probability_says():
    for gross in (-.05, 0.0, .002):
        rec = D.describe(row(grossExpectedAlpha=gross, probabilityNetOutperform=.9, probabilityLower=.8), cost=.002)
        assert rec["expectedValueClass"] == D.BENCHMARK
    assert D.describe(row(grossExpectedAlpha=-.01, probabilityNetOutperform=.7), cost=0.)[
        "distributionState"] == D.EV_NOT_POSITIVE_PROB_ABOVE_HALF


def test_zero_positive_names_is_valid():
    recs = [(f"S{i}", D.describe(row(grossExpectedAlpha=-.01 * (i + 1)), cost=.002)) for i in range(8)]
    assert D.opportunity_surface(recs) == {"positiveExpectedAlpha": [], "count": 0,
                                           "state": "NO_POSITIVE_EXPECTED_ALPHA"}


def test_no_top_n_quota_or_invested_fraction(spec):
    recs = [(f"US{i}", D.describe(row(grossExpectedAlpha=.01 + i / 1000), cost=.002)) for i in range(17)]
    recs += [("KR0", D.describe(row(grossExpectedAlpha=-.01), cost=.004))]
    surface = D.opportunity_surface(recs)
    assert surface["count"] == 17 and "KR0" not in surface["positiveExpectedAlpha"]
    assert surface["positiveExpectedAlpha"][0] == "US16"   # ordered by expectedNetAlpha, not cut
    contract = spec["decisionContract"]
    for key in ("fixedTopN", "regionQuota", "investedFraction", "minimumAlphaHurdle",
                "probabilityHurdle", "lowerBoundHurdle", "portfolioValue", "orderNotional"):
        assert contract[key] is None


def test_tiny_positive_ev_counts_no_hurdle():
    rec = D.describe(row(grossExpectedAlpha=.0020001, grossExpectedAlphaLower=-.5,
                         probabilityNetOutperform=.01, probabilityLower=.0), cost=.002)
    assert rec["expectedValueClass"] == D.POSITIVE


@pytest.mark.parametrize("key,where", [("minimumEdge", "decisionContract"), ("probabilityHurdle", "decisionContract"),
                                       ("lowerBoundHurdle", "decisionContract"), ("fixedTopN", "decisionContract"),
                                       ("regionQuota", "decisionContract"), ("investedFraction", "decisionContract"),
                                       ("kellyFraction", "carriedFromV2")])
def test_spec_reintroducing_a_hurdle_or_sizing_parameter_is_refused(tmp_path, spec, key, where):
    path = sealed_copy(tmp_path, spec)
    value = deepcopy(spec)
    value[where][key] = 0.02
    path.write_bytes(V1S.canonical(value))
    path.with_suffix(".sha256").write_text(S.digest(value))
    with pytest.raises(ValueError, match="FORBIDDEN_DECISION_PARAMETER"):
        S.load_sealed(path, expected_hash=S.digest(value), root=tmp_path)


def test_probability_and_uncertainty_never_define_existence():
    import inspect
    src = inspect.getsource(D.expected_value_class)
    assert "probab" not in src.lower() and "lower" not in src.lower()
    for p in (0.0, .2, .49, .5, .51, 1.0):
        for lower in (-1.0, -.001, .001):
            assert D.describe(row(probabilityNetOutperform=p, grossExpectedAlphaLower=lower), cost=.002)[
                "expectedValueClass"] == D.POSITIVE


def test_transaction_cost_reduces_expected_net_alpha(spec):
    costs = spec["carriedFromV2"]["transactionCosts"]
    kr13, kr25 = D.round_trip_cost("KR", "2013-06-01", costs), D.round_trip_cost("KR", "2025-06-01", costs)
    assert kr13 == pytest.approx(.0041) and kr25 == pytest.approx(.0026)
    assert D.round_trip_cost("US", "2020-01-01", costs) == pytest.approx(.00163)
    assert D.describe(row(grossExpectedAlpha=.004), cost=kr13)["expectedValueClass"] == D.BENCHMARK
    assert D.describe(row(grossExpectedAlpha=.004), cost=kr25)["expectedValueClass"] == D.POSITIVE
    for date in ("2013-01-01", "2019-06-03", "2023-12-31", "2026-02-01", None):
        assert D.dated_cost_policy(costs["KR"], date) == PV._dated_cost_policy(costs["KR"], date)


def test_probability_and_uncertainty_fields_remain_and_are_distinct():
    rec = D.describe(row(), cost=.002)
    for key in ("probabilityNetOutperform", "probabilityLower", "probabilityUpper",
                "expectedNetAlphaLower", "expectedNetAlphaUpper", "predictiveResidualRms"):
        assert rec[key] is not None
    kinds = rec["uncertaintyKinds"]
    assert kinds["expectedNetAlphaLower"].startswith("FITTED_VALUE_SAMPLING")
    assert kinds["predictiveResidualRms"].startswith("PREDICTIVE_OUTCOME_DISPERSION")
    assert rec["predictiveResidualRms"] == .09 and rec["expectedNetAlphaLower"] == pytest.approx(.008)


def test_alpha_layer_has_no_sizing_or_allocation(spec):
    rec = D.describe(row(), cost=.002)
    assert not D.PORTFOLIO_FIELDS & rec.keys()
    tree = ast.parse((ROOT / "pipeline/alpha_opportunity_v3_decision.py").read_text())
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    imports = {a.name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
    assert not {"kelly_portfolio", "select_portfolio_by_scores", "baseline_weights"} & (names | imports)


# --------------------------------------------------------------------------- #
# Survivorship
# --------------------------------------------------------------------------- #
def _panel(days, *, until=None, skip=()):
    return {str(d.date()): (True, True) for d in days if (until is None or str(d.date()) <= until)
            and str(d.date()) not in skip}


def _fixture():
    days = RC.sessions("2019-06-01", "2021-12-31", "US")
    snaps = [{"date": "2019-12-27", "members": ["ALIVE", "DIED", "GONE", "HALT"]},
             {"date": "2020-12-24", "members": ["ALIVE", "HALT", "NEW"]}]
    avail = {"ALIVE": _panel(days), "NEW": _panel(days), "DIED": _panel(days, until="2020-06-30"),
             "HALT": _panel(days, skip={"2020-03-10"})}
    return days, snaps, avail


def test_missing_former_members_are_counted_not_dropped():
    days, snaps, avail = _fixture()
    audit = A.audit_region("US", snaps, avail, {"ALIVE": 3, "NEW": 1}, start="2020-01-01",
                           through="2021-06-30", sessions=days)
    s = audit["sampleSurvivorship"]
    assert s["noPanelNames"] == 1 and s["noPanelDeparted"] == 1 and s["noPanelCurrent"] == 0
    assert audit["_sets"]["noPanel"] == ["GONE"]
    assert audit["memberDates"] == sum(y["memberDates"] for y in audit["memberDatesByYear"].values())
    assert audit["memberDatesByYear"]["2020"]["NO_PANEL"] > 0
    assert audit["terminations"]["terminatedInPanel"] == 1
    v = A.region_verdict(audit)
    assert not v["survivorshipSafe"] and "MISSINGNESS_CONCENTRATED_IN_DEPARTED_MEMBERS" in v["defects"]
    assert "TERMINATED_NAMES_LACK_TOTAL_RETURN_LINEAGE" in v["defects"]


def test_training_and_endpoint_missingness_are_separate_and_stress_is_not_repair():
    days, snaps, avail = _fixture()
    audit = A.audit_region("US", snaps, avail, {"ALIVE": 3, "NEW": 1, "DIED": 2}, start="2020-01-01",
                           through="2021-06-30", sessions=days)
    # DIED terminates inside the sample: that is ENDPOINT missingness on a sampled name.
    assert audit["endpointSurvivorship"]["21"]["missingOnTerminatedNames"] > 0
    # GONE never enters the sample: no endpoint exists to stress, and the verdict stays unsafe.
    assert "GONE" not in {t for t in audit["_sets"]["terminated"]}
    assert not A.region_verdict(audit)["survivorshipSafe"]
    spec = S.read_json(S.DEFAULT_SPEC)
    assert spec["survivorship"]["endpointStressIsNotTrainingRepair"] is True


def test_no_forward_fill_and_no_terminal_zero():
    days, snaps, avail = _fixture()
    assert A.classify(avail["HALT"], "2020-03-10", [str(d.date()) for d in days if str(d.date()) <= "2020-03-10"][-20:]) \
        == A.NO_SIGNAL_DATE_PRICE
    window = [str(d.date()) for d in days if str(d.date()) <= "2020-03-13"][-20:]
    assert A.classify(avail["HALT"], "2020-03-13", window) == A.NOT_CONTINUOUSLY_TRADED
    assert A.classify(avail["DIED"], "2020-07-10", window) == A.NO_SIGNAL_DATE_PRICE
    assert A.classify(None, "2020-07-10", window) == A.NO_PANEL
    assert A.availability_from_rows([{"ticker": "X", "date": "2020-01-02", "Close": 0.0, "Volume": 5}]) == {
        "X": {"2020-01-02": (False, True)}}


def test_no_current_universe_substitution_and_strictly_earlier_membership():
    days, snaps, avail = _fixture()
    assert A.snapshot_on(snaps, "2020-12-24")["members"] == snaps[0]["members"]
    assert A.snapshot_on(snaps, "2020-12-31")["members"] == snaps[1]["members"]
    assert A.snapshot_on(snaps, "2019-12-27") is None
    ref = RAF.MembershipSnapshots(snaps)
    for d in ("2020-01-03", "2020-12-24", "2020-12-31"):
        assert A.snapshot_on(snaps, d) == ref.on(d)
    assert A.weekly_grid(RC.sessions("2020-01-01", "2021-03-01", "US"), "2021-02-26") == \
        RAF.weekly_grid("2020-01-01", "2021-02-26", "US")
    with pytest.raises(ValueError, match="PIT_MEMBERSHIP_MISSING"):
        A.audit_region("US", snaps, avail, {}, start="2019-06-01", through="2020-01-31", sessions=days)


def test_restricted_window_needs_clean_trailing_years_not_a_tolerance():
    def fake(shares):
        return {"memberDatesByYear": {y: {"departedOnlyNoPanelPct": v} for y, v in shares.items()}}
    declining = {"2019": 16.6, "2020": 13.0, "2023": 4.8, "2025": 2.2, "2026": 0.65}
    assert A.restricted_window_exists(fake(declining))["structuralCutoffExists"] is False
    step = {"2019": 16.6, "2020": 13.0, "2021": 0.0, "2022": 0.0}
    assert A.restricted_window_exists(fake(step))["trailingCleanYears"] == ["2021", "2022"]
    assert A.restricted_window_exists(fake({"2019": 0.0, "2020": 0.0}))["structuralCutoffExists"] is False


def test_both_regions_receive_the_same_checks(spec):
    audit = json.loads(AUDIT.read_text())
    assert set(audit["regions"]) == set(audit["verdicts"]) == set(audit["restrictedWindow"]) == {"US", "KR"}
    assert set(audit["regions"]["US"]) == set(audit["regions"]["KR"])
    assert audit["historicalOutcomesComputed"] is False and audit["returnsComputed"] is False
    assert audit["labelsConstructed"] is False and audit["modelsTrained"] is False
    us, kr = audit["regions"]["US"], audit["regions"]["KR"]
    assert us["sampleSurvivorship"]["noPanelDeparted"] == 212 and us["sampleSurvivorship"]["noPanelCurrent"] == 0
    assert us["universe"]["union"] == 827 and us["sampleSurvivorship"]["departedExitIdentityUnresolved"] == 181
    assert us["terminations"]["terminatedInPanel"] == 0
    assert kr["sampleSurvivorship"]["noPanelNames"] == 0 and kr["terminations"]["terminatedInPanel"] == 22
    assert kr["totalReturnLineage"]["terminatedWithDividendEvents"] == 0
    assert audit["verdicts"]["US"]["defects"] == spec["survivorship"]["regions"]["US"]["defects"]
    assert audit["verdicts"]["KR"]["defects"] == spec["survivorship"]["regions"]["KR"]["defects"]


def test_blocked_periods_cannot_enter_training_or_execution(spec, monkeypatch):
    assert S.preregistration_status(spec) == "BLOCKED_BY_DATA_INTEGRITY"
    assert all(r["verdict"] == "BLOCKED_BY_DATA_INTEGRITY" for r in spec["survivorship"]["regions"].values())
    with pytest.raises(ValueError, match="BLOCKED_BY_DATA_INTEGRITY"):
        S.require_execution(spec, reviewed=True, branch="refs/heads/main")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    with pytest.raises(ValueError, match="BLOCKED_BY_DATA_INTEGRITY"):
        CLI.main(["--sealed-sha256", seal(), "--execute", "--reviewed"])


def test_status_cannot_be_flipped_without_resealing(tmp_path, spec):
    value = deepcopy(spec)
    value["designBlockers"] = []
    with pytest.raises(ValueError, match="DISAGREES"):
        S.preregistration_status(value)
    path = sealed_copy(tmp_path, spec)
    value["preregistrationStatus"] = S.READY
    path.write_bytes(V1S.canonical(value))
    with pytest.raises(ValueError, match="SEALED_SPEC_CHANGED"):
        S.load_sealed(path, expected_hash=seal(), root=tmp_path)


# --------------------------------------------------------------------------- #
# Dependency closure
# --------------------------------------------------------------------------- #
UNRELATED = ("pipeline/kelly_portfolio.py", "pipeline/longterm.py", "pipeline/replay_valuation.py",
             "pipeline/selection_null.py", "pipeline/portfolio_validation.py")


def test_sealed_set_is_exactly_the_recomputed_closure(spec):
    assert sorted(spec["dependencyHashes"]) == S.sealed_file_set(spec)
    for rel in UNRELATED + ("pipeline/regional_alpha_features.py", "pipeline/historical_replay.py",
                            "pipeline/dart_ownership_events.py", "pipeline/guru_13f_store.py"):
        assert rel not in spec["dependencyHashes"]
    assert not any("dart-ownership" in k for k in spec["dependencyHashes"])
    assert all("dart-ownership" not in k for k in spec["futureExecutionInputs"]["gitBlobSha1"])


def test_unrelated_module_change_does_not_break_seal(tmp_path, spec):
    path = sealed_copy(tmp_path, spec, extra=UNRELATED)
    for rel in UNRELATED:
        (tmp_path / rel).write_text("# unrelated production edit\n")
    assert S.load_sealed(path, expected_hash=seal(), root=tmp_path)["studyId"] == S.STUDY


@pytest.mark.parametrize("rel", ["pipeline/alpha_opportunity_v3_decision.py", "pipeline/replay_calendar.py",
                                 "pipeline/replay_inputs.py", "scripts/run_alpha_opportunity_model_v3.py",
                                 "docs/results/alpha-opportunity-model-v3-survivorship-audit.json",
                                 "pipeline/alpha_opportunity_v3_identity.py"])
def test_real_dependency_change_breaks_seal(tmp_path, spec, rel):
    path = sealed_copy(tmp_path, spec)
    (tmp_path / rel).write_text((tmp_path / rel).read_text() + "\n# edit\n")
    with pytest.raises(ValueError, match="SEALED_DEPENDENCY_CHANGED"):
        S.load_sealed(path, expected_hash=seal(), root=tmp_path)


def test_new_unsealed_import_breaks_seal(tmp_path, spec):
    path = sealed_copy(tmp_path, spec, extra=("pipeline/kelly_portfolio.py",))
    target = tmp_path / "pipeline/alpha_opportunity_v3_decision.py"
    target.write_text(target.read_text() + "\n\ndef _x():\n    from . import kelly_portfolio  # noqa\n")
    with pytest.raises(ValueError, match="DEPENDENCY_CLOSURE_CHANGED"):
        S.load_sealed(path, expected_hash=seal(), root=tmp_path)


def test_lazy_imports_count_in_the_closure(tmp_path):
    (tmp_path / "pipeline").mkdir()
    (tmp_path / "pipeline/__init__.py").write_text("")
    (tmp_path / "pipeline/a.py").write_text("def f():\n    from . import b\n")
    (tmp_path / "pipeline/b.py").write_text("from pipeline import c\n")
    (tmp_path / "pipeline/c.py").write_text("")
    (tmp_path / "pipeline/d.py").write_text("")
    assert S.import_closure(["pipeline/a.py"], tmp_path) == [
        "pipeline/__init__.py", "pipeline/a.py", "pipeline/b.py", "pipeline/c.py"]


# --------------------------------------------------------------------------- #
# No outcomes, no workflow, no production coupling
# --------------------------------------------------------------------------- #
def test_no_v3_workflow_and_readiness_artifact_matches(spec):
    assert not (ROOT / ".github/workflows/alpha-opportunity-model-v3.yml").exists()
    assert spec["executionWorkflow"] is None
    report = S.readiness(spec, seal())
    assert S.read_json(ROOT / "docs/results/alpha-opportunity-model-v3-readiness.json") == report
    assert report["historicalOutcomesComputed"] is False and report["historicalModelsTrained"] is False


def test_cli_readiness_is_deterministic(capsys):
    assert CLI.main(["--sealed-sha256", seal()]) == 0
    first = capsys.readouterr().out
    CLI.main(["--sealed-sha256", seal()])
    assert capsys.readouterr().out == first
    assert json.loads(first)["preregistrationStatus"] == "BLOCKED_BY_DATA_INTEGRITY"


def test_no_production_module_imports_v3():
    for path in (ROOT / "pipeline").glob("*.py"):
        if path.stem.startswith("alpha_opportunity_"):
            continue
        text = path.read_text()
        assert "alpha_opportunity_v3" not in text, path


def test_survivorship_audit_reads_no_returns():
    src = (ROOT / "pipeline/alpha_opportunity_v3_survivorship.py").read_text()
    src += (ROOT / "scripts/audit_alpha_opportunity_v3_survivorship.py").read_text()
    for forbidden in ("pct_change", "target_at", "forwardRelativeReturn", "excessReturn", "/ a - 1"):
        assert forbidden not in src


# --------------------------------------------------------------------------- #
# Terminology: probability is not a median
# --------------------------------------------------------------------------- #
def test_probability_terminology_never_claims_a_median(spec):
    for state in D.DISTRIBUTION_STATES:
        assert "MEDIAN" not in state and "OUTPERFORM_PROBABILITY" in state
    prob = spec["decisionContract"]["probability"]
    assert not any("MEDIAN" in st for st in prob["states"])
    assert "median" not in prob["meaning"].lower() and "median" in prob["notA"].lower()
    import re
    for rel in ("docs/alpha-opportunity-model-v3-preregistration.md", "docs/alpha-opportunity-v3-data-repair-plan.md",
                "pipeline/alpha_opportunity_v3_decision.py"):
        text = re.sub(r"[*_`]", "", (ROOT / rel).read_text().lower())
        for claim in ("predicted median", "positive median", "negative median", "median net alpha",
                      "median of the predicted", "median is positive", "median below"):
            assert claim not in text, (rel, claim)
    rec = D.describe(row(probabilityNetOutperform=.3), cost=.002)
    assert rec["expectedValueClass"] == D.POSITIVE
    assert rec["distributionState"] == D.EV_POSITIVE_PROB_NOT_ABOVE_HALF


# --------------------------------------------------------------------------- #
# Identity
# --------------------------------------------------------------------------- #
from pipeline import alpha_opportunity_v3_identity as ID  # noqa: E402


def _snaps(*members):
    return [{"date": f"2020-0{i + 1}-01", "members": list(m)} for i, m in enumerate(members)]


def _index(snaps, table):
    return [{t: table.get((i, t), (t, t + " Inc", None)) for t in s["members"]} for i, s in enumerate(snaps)]


FULL = {"2019-12-02": (True, True), "2020-01-02": (True, True), "2020-06-01": (True, True)}


def test_malformed_identifier_never_silently_becomes_a_ticker():
    snaps = _snaps({"AAL", "X"}, {"American Airlines Group", "X"}, {"AAL", "X"})
    idx = _index(snaps, {(0, "AAL"): ("AAL", "American Airlines Group", None),
                         (2, "AAL"): ("AAL", "American Airlines Group", None)})
    recs, mapping = ID.classify(snaps, {"AAL": FULL, "X": FULL}, index=idx, through="2020-06-30")
    assert recs["American Airlines Group"]["category"] == ID.IDENTIFIER_MALFORMED_RESOLVED
    assert mapping == {"American Airlines Group": "AAL"}
    # Not bracketed on both sides: stays unresolved, never guessed.
    snaps2 = _snaps({"X"}, {"American Airlines Group", "X"}, {"AAL", "X"})
    recs2, mapping2 = ID.classify(snaps2, {"AAL": FULL, "X": FULL}, index=_index(snaps2, {}), through="2020-06-30")
    assert recs2["American Airlines Group"]["category"] == ID.IDENTIFIER_MALFORMED_UNRESOLVED and mapping2 == {}
    assert ID.pricing_symbol("American Airlines Group", recs2) is None


def test_reused_ticker_never_inherits_a_later_issuers_panel():
    snaps = _snaps({"OLD", "X"}, {"X"}, {"X"})
    later_issuer = {"2020-05-01": (True, True)}           # starts after OLD left
    recs, _ = ID.classify(snaps, {"OLD": later_issuer, "X": FULL}, index=_index(snaps, {}), through="2020-06-30")
    assert recs["OLD"]["category"] == ID.TICKER_REUSE_DIFFERENT_ISSUER
    assert "PANEL_POSTDATES_MEMBERSHIP" in recs["OLD"]["flags"]
    assert ID.pricing_symbol("OLD", recs) is None


def test_same_security_rename_is_distinct_from_reuse_and_priced_by_successor():
    snaps = _snaps({"FI", "X"}, {"FISV", "X"}, {"FISV", "X"})
    idx = _index(snaps, {(0, "FI"): ("FI", "Fiserv", "798354"), (1, "FISV"): ("FISV", "Fiserv", "798354"),
                         (2, "FISV"): ("FISV", "Fiserv", "798354")})
    recs, _ = ID.classify(snaps, {"FISV": FULL, "X": FULL}, index=idx, through="2020-06-30")
    assert recs["FI"]["category"] == ID.SAME_SECURITY_RENAME and recs["FI"]["basis"] == "SAME_CIK"
    assert ID.pricing_symbol("FI", recs) == "FISV"


def test_acquired_company_is_never_replaced_by_its_acquirer():
    snaps = _snaps({"TGT", "ACQ0"}, {"ACQ"}, {"ACQ"})
    idx = _index(snaps, {(0, "TGT"): ("TGT", "Target Co", "111"), (1, "ACQ"): ("ACQ", "Acquirer Co", "222")})
    recs, _ = ID.classify(snaps, {"ACQ": FULL}, index=idx, through="2020-06-30")
    assert recs["TGT"]["category"] == ID.DEPARTED_NO_PANEL_REASON_UNRESOLVED
    assert ID.pricing_symbol("TGT", recs) is None
    recs2, _ = ID.classify(snaps, {"ACQ": FULL}, index=idx, through="2020-06-30",
                           corporate_actions=[{"ticker": "TGT", "type": "CASH_AND_STOCK_MERGER", "successorTicker": "ACQ"}])
    assert recs2["TGT"]["category"] == ID.ACQUIRED_OR_MERGED_TERMINATED and ID.pricing_symbol("TGT", recs2) is None


def test_share_classes_with_one_cik_are_never_joined():
    snaps = _snaps({"GOOG", "GOOGL"}, {"GOOGL"}, {"GOOGL"})
    idx = _index(snaps, {(0, "GOOG"): ("GOOG", "Alphabet C", "1652044"), (0, "GOOGL"): ("GOOGL", "Alphabet A", "1652044"),
                         (1, "GOOGL"): ("GOOGL", "Alphabet A", "1652044"), (2, "GOOGL"): ("GOOGL", "Alphabet A", "1652044")})
    recs, _ = ID.classify(snaps, {"GOOGL": FULL}, index=idx, through="2020-06-30")
    assert recs["GOOG"]["category"] != ID.SAME_SECURITY_RENAME and ID.pricing_symbol("GOOG", recs) is None


def test_ambiguous_successors_stay_unresolved():
    snaps = _snaps({"OLD"}, {"NEW1", "NEW2"}, {"NEW1", "NEW2"})
    idx = _index(snaps, {(0, "OLD"): ("OLD", "Same Name", None), (1, "NEW1"): ("NEW1", "Same Name", None),
                         (1, "NEW2"): ("NEW2", "Same Name", None)})
    recs, _ = ID.classify(snaps, {"NEW1": FULL, "NEW2": FULL}, index=idx, through="2020-06-30")
    assert recs["OLD"]["category"] == ID.DEPARTED_NO_PANEL_REASON_UNRESOLVED
    assert "RENAME_AMBIGUOUS" in recs["OLD"]["flags"] and ID.pricing_symbol("OLD", recs) is None


def test_identity_evidence_reproduces_pinned_membership():
    import gzip
    ev = json.loads(gzip.decompress((ROOT / "research_specs/alpha-opportunity-model-v3-us-identity-evidence.json.gz").read_bytes()))
    pinned = json.loads(gzip.decompress((ROOT / "research_specs/alpha-opportunity-model-v1-us-membership.json.gz").read_bytes()))
    assert ev["pinnedMembershipSha256"] == V1S.file_hash(ROOT / "research_specs/alpha-opportunity-model-v1-us-membership.json.gz")
    assert [s["sourceCommit"] for s in ev["snapshots"]] == [s["sourceCommit"] for s in pinned["snapshots"]]
    for e, p in zip(ev["snapshots"], pinned["snapshots"]):
        assert sorted({ev["rows"][i][0].replace(".", "-") for i in e["rows"]}) == p["members"]
    raw = [ev["rows"][i] for e in ev["snapshots"] for i in e["rows"]]
    assert ["American Airlines Group", "reports", None] in raw
    assert any(r[0] == "RVTY (Previously PKI)" for r in raw)


def test_us_counts_reconcile_v2_and_first_v3_seal_deterministically():
    import gzip
    audit = json.loads(AUDIT.read_text())
    rec = audit["usCountReconciliation"]
    assert rec["v2InputAudit"] == {**rec["v2InputAudit"], "membershipUnion": 829, "noPanelNames": 194}
    assert rec["v3FirstSeal"]["union"] == 828 and rec["v3FirstSeal"]["noPanelNames"] == 195
    st = rec["steps"]
    assert st["minusResolvedMalformedKeys"] == ["American Airlines Group"]
    assert st["firstSealNoPanel"] - len(st["minusResolvedMalformedKeys"]) - len(
        st["minusRenamesPricedThroughSuccessor"]) + len(st["plusSymbolsWhosePanelBelongsToALaterSecurity"]) \
        == st["equals"] == st["auditNoPanel"] == 212
    malformed = rec["malformedKeys"]
    assert malformed["American Airlines Group"]["resolvedTo"] == "AAL" and malformed["American Airlines Group"]["reachableFromGrid"]
    assert malformed["RVTY (Previously PKI)"]["resolvedTo"] == "RVTY" and not malformed["RVTY (Previously PKI)"]["reachableFromGrid"]
    # The raw unions are recomputable from the pinned file alone.
    pinned = json.loads(gzip.decompress((ROOT / "research_specs/alpha-opportunity-model-v1-us-membership.json.gz").read_bytes()))["snapshots"]
    assert len(set().union(*[set(s["members"]) for s in pinned])) == 829
    grid = A.weekly_grid([d for d in RC.sessions("2012-01-01", "2027-12-31", "US") if str(d.date()) >= "2013-01-01"], "2026-09-14")
    assert len(set().union(*[set(A.snapshot_on(pinned, g)["members"]) for g in grid])) == 828


def test_kr_terminations_listed_and_untyped(spec):
    audit = json.loads(AUDIT.read_text())
    rows = audit["krTerminations"]
    assert len(rows) == 22 and {r["terminationType"] for r in rows} == {"TERMINATION_TYPE_UNRESOLVED"}
    assert all(r["dividendEvents"] == 0 and r["krxName"] for r in rows)
    ids = {b["id"] for b in spec["designBlockers"]}
    assert {"KR_TERMINATED_NAME_DIVIDEND_LINEAGE_ABSENT", "KR_TERMINAL_CONSIDERATION_UNRESOLVED",
            "US_EXIT_IDENTITY_UNRESOLVED", "US_DELISTED_MEMBER_HISTORY_ABSENT"} <= ids
    assert (ROOT / "docs/alpha-opportunity-v3-data-repair-plan.md").exists()
