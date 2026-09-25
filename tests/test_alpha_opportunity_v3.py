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
    assert rec["distributionState"] == D.MEAN_POSITIVE_MEDIAN_NOT
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
        "distributionState"] == D.MEAN_NOT_MEDIAN_POSITIVE


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
    assert us["sampleSurvivorship"]["noPanelDeparted"] == 195 and us["sampleSurvivorship"]["noPanelCurrent"] == 0
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
                                 "docs/results/alpha-opportunity-model-v3-survivorship-audit.json"])
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
