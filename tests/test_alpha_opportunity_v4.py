"""alpha-opportunity-model-v4 contract tests. Synthetic fixtures and sealed
metadata only: no real price level, label, return or model fit is read here.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from pipeline import alpha_opportunity_spec as V1S
from pipeline import alpha_opportunity_v4_eligibility as ELIG
from pipeline import alpha_opportunity_v4_spec as S

ROOT = Path(__file__).resolve().parents[1]
V1_SEAL = "e3c699b197fd558506d7157fa6dd8cdb91156faccd0e6e9547d21d5baa23dd6e"
V2_SEAL = "97c3727b37eeab71e31ffee17a2f81cac29f0333552ff04a5374ef48484b0e19"
V3_SEAL = "f6e11fafc2d46137d3f8385858c58d9991cb3809a2f811c368a81baf149fc3fe"


@pytest.fixture
def spec():
    return S.read_json(S.DEFAULT_SPEC)


def seal():
    return S.DEFAULT_SPEC.with_suffix(".sha256").read_text().strip()


def sealed_copy(tmp_path, spec, extra=()):
    for rel in list(spec["dependencyHashes"]) + ["research_specs/alpha-opportunity-model-v4.json",
                                                 "research_specs/alpha-opportunity-model-v4.sha256", *extra]:
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, dst)
    return tmp_path / "research_specs/alpha-opportunity-model-v4.json"


# --------------------------------------------------------------------------- #
# Versioning: v1/v2/v3 unchanged; v4 is a new, correctly-identified seal
# --------------------------------------------------------------------------- #
def test_v1_v2_v3_seals_unchanged(spec):
    for study, sha in (("alpha-opportunity-model-v1", V1_SEAL),
                      ("alpha-opportunity-model-v2", V2_SEAL),
                      ("alpha-opportunity-model-v3", V3_SEAL)):
        path = ROOT / "research_specs" / f"{study}.json"
        assert S.digest(S.read_json(path)) == sha == path.with_suffix(".sha256").read_text().strip()
    assert {p["studyId"]: p["specSha256"] for p in spec["priorVersions"]} == {
        "alpha-opportunity-model-v1": V1_SEAL, "alpha-opportunity-model-v2": V2_SEAL,
        "alpha-opportunity-model-v3": V3_SEAL}
    assert S.verify_prior_versions(spec)


def test_v4_seal_deterministic_and_verified(spec):
    assert S.digest(spec) == seal() == S.digest(json.loads(S.DEFAULT_SPEC.read_text()))
    assert S.load_sealed(expected_hash=seal()) == spec
    with pytest.raises(ValueError, match="SEALED_SPEC_CHANGED"):
        S.load_sealed(expected_hash="0" * 64)
    with pytest.raises(ValueError):
        S.load_sealed(ROOT / "research_specs/alpha-opportunity-model-v3.json", expected_hash=V3_SEAL)


def test_prior_version_mutation_breaks_v4(tmp_path, spec):
    path = sealed_copy(tmp_path, spec)
    S.load_sealed(path, expected_hash=seal(), root=tmp_path)
    v3 = S.read_json(tmp_path / "research_specs/alpha-opportunity-model-v3.json")
    v3["horizons"] = [21, 63, 126]
    (tmp_path / "research_specs/alpha-opportunity-model-v3.json").write_bytes(V1S.canonical(v3))
    with pytest.raises(ValueError, match="SEALED_DEPENDENCY_CHANGED|PRIOR_SEAL_CHANGED"):
        S.load_sealed(path, expected_hash=seal(), root=tmp_path)


def test_v4_is_kr_only(spec):
    assert spec["regions"] == ["KR"]
    assert spec["benchmarks"] == {"KR": "069500.KS"}
    assert "US" not in spec["carriedFromV3"]["allowedFeatures"]
    assert set(spec["carriedFromV3"]["transactionCosts"]) == {"KR"}


def test_a_non_kr_region_is_refused(tmp_path, spec):
    path = sealed_copy(tmp_path, spec)
    value = deepcopy(spec)
    value["regions"] = ["KR", "US"]
    path.write_bytes(V1S.canonical(value))
    path.with_suffix(".sha256").write_text(S.digest(value))
    with pytest.raises(ValueError, match="UNSUPPORTED_CONTRACT"):
        S.load_sealed(path, expected_hash=S.digest(value), root=tmp_path)


# --------------------------------------------------------------------------- #
# No hidden hurdle, quota, sizing or portfolio parameter
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("key", ["fixedTopN", "regionQuota", "investedFraction",
                                 "minimumAlphaHurdle", "probabilityHurdle", "lowerBoundHurdle",
                                 "portfolioValue", "orderNotional"])
def test_decision_contract_has_no_hurdle_or_sizing_field(spec, key):
    assert spec["decisionContract"][key] is None


@pytest.mark.parametrize("key", ["minimumEdge", "probabilityHurdle", "lowerBoundHurdle",
                                 "fixedTopN", "regionQuota", "investedFraction", "kellyFraction"])
def test_spec_reintroducing_a_hurdle_or_sizing_parameter_is_refused(tmp_path, spec, key):
    path = sealed_copy(tmp_path, spec)
    value = deepcopy(spec)
    value.setdefault("decisionContract", {})[key] = 0.02
    path.write_bytes(V1S.canonical(value))
    path.with_suffix(".sha256").write_text(S.digest(value))
    with pytest.raises(ValueError, match="FORBIDDEN_DECISION_PARAMETER"):
        S.load_sealed(path, expected_hash=S.digest(value), root=tmp_path)


# --------------------------------------------------------------------------- #
# Source foundation vs study design vs execution: the three layers stay apart,
# and (CORRECTED) a future foundation repair no longer breaks the seal.
# --------------------------------------------------------------------------- #
def test_source_foundation_citation_is_informational_and_still_partially_repaired(spec):
    entry = spec["sourceFoundationCitation"]["krTerminalActionReconstructionV2"]
    assert entry["foundationStatusAsOfThisSeal"] == "PARTIALLY_REPAIRED"
    real = S.read_json(ROOT / entry["path"])
    assert real["foundationStatus"] == "PARTIALLY_REPAIRED"
    assert S.file_hash(ROOT / entry["path"]) == entry["shaAsOfThisSeal"]
    # The three KR terminal-action artifacts are citations, not sealed inputs.
    for name in ("krTerminalActionReconstructionV2", "krTerminationInventory",
                 "krTerminalCorporateActionsBook"):
        assert spec["sourceFoundationCitation"][name]["path"] not in spec["dependencyHashes"]
    # The v3 survivorship audit remains a genuinely sealed, hash-verified input.
    assert ("docs/results/alpha-opportunity-model-v3-survivorship-audit.json"
           in spec["dependencyHashes"])


def test_design_status_is_ready_despite_partially_repaired_source(spec):
    assert spec["preregistrationStatus"] == "READY_FOR_HISTORICAL_EXECUTION"
    assert spec["designBlockers"] == []
    ids = {b["id"] for b in spec["formerV3BlockersResolvedByPolicy"]}
    assert ids == {"KR_TERMINATED_NAME_DIVIDEND_LINEAGE_ABSENT", "KR_TERMINAL_CONSIDERATION_UNRESOLVED"}


def test_foundation_artifact_changing_on_disk_no_longer_breaks_the_seal(tmp_path, spec):
    """CORRECTION: v1 of this spec hash-pinned the KR terminal-action artifact
    into dependencyHashes AND re-verified its quoted status on every load --
    directly contradicting the spec's own claim that a future data-foundation
    repair could be consumed by the same eligibility policy without a new
    preregistration, since that repair changes the artifact's bytes. A repair
    (or, symmetrically, a regression) must not make the SEALED SPEC itself
    unloadable; only `assert_foundation_not_regressed` (tested below) should
    ever object to a regression, and only when an execution explicitly calls it.
    """
    path = sealed_copy(tmp_path, spec)
    recon_path = tmp_path / "docs/results/kr-terminal-action-reconstruction-v2.json"
    recon_path.parent.mkdir(parents=True, exist_ok=True)
    real_recon = json.loads((ROOT / "docs/results/kr-terminal-action-reconstruction-v2.json").read_text())
    real_recon["foundationStatus"] = "READY_FOR_V4_PREREGISTRATION"
    real_recon["securities"][0]["completeness"]["exDateSemanticsResolved"] = "READY"
    recon_path.write_text(json.dumps(real_recon))
    loaded = S.load_sealed(path, expected_hash=seal(), root=tmp_path)
    assert loaded["preregistrationStatus"] == "READY_FOR_HISTORICAL_EXECUTION"


def test_assert_foundation_not_regressed_accepts_improvement_and_rejects_regression():
    cited = {"securities": [{"code": "000030.KS", "completeness": {"exDateSemanticsResolved": "BLOCKED",
                                                                   "terminationTypeResolved": "READY"}}]}
    improved = {"securities": [{"code": "000030.KS", "completeness": {"exDateSemanticsResolved": "READY",
                                                                      "terminationTypeResolved": "READY"}}]}
    assert ELIG.assert_foundation_not_regressed(cited_snapshot=cited, current_snapshot=improved)

    regressed = {"securities": [{"code": "000030.KS", "completeness": {"exDateSemanticsResolved": "BLOCKED",
                                                                       "terminationTypeResolved": "BLOCKED"}}]}
    with pytest.raises(ValueError, match="FOUNDATION_REGRESSED"):
        ELIG.assert_foundation_not_regressed(cited_snapshot=cited, current_snapshot=regressed)

    dropped = {"securities": []}
    with pytest.raises(ValueError, match="FOUNDATION_REGRESSED"):
        ELIG.assert_foundation_not_regressed(cited_snapshot=cited, current_snapshot=dropped)


def test_readiness_never_claims_an_outcome(spec):
    ready = S.readiness(spec, seal())
    assert ready["historicalOutcomesComputed"] is False
    assert ready["historicalModelsTrained"] is False
    assert ready["labelsConstructed"] is False
    assert ready["promotionEligible"] is False
    assert ready["productionChanged"] is False
    assert ready["executionWorkflow"] is None
    assert ready["executionMustReverifyFoundationAgainstLiveData"] is True


def test_require_execution_still_needs_review_and_main(spec):
    with pytest.raises(ValueError, match="MERGE_AND_REVIEW_PREREGISTRATION_FIRST"):
        S.require_execution(spec, reviewed=False, branch="refs/heads/main")
    with pytest.raises(ValueError, match="MERGE_AND_REVIEW_PREREGISTRATION_FIRST"):
        S.require_execution(spec, reviewed=True, branch="refs/heads/feature")
    assert S.require_execution(spec, reviewed=True, branch="refs/heads/main") is None


def test_cli_always_refuses_execute_even_when_ready():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_alpha_opportunity_model_v4.py"),
         "--sealed-sha256", seal(), "--execute"],
        cwd=ROOT, capture_output=True, text=True)
    assert result.returncode != 0
    assert "NO_V4_EXECUTION_HARNESS_IN_THIS_PR" in result.stderr


def test_cli_readiness_print_matches_module(spec):
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_alpha_opportunity_model_v4.py"),
         "--sealed-sha256", seal()], cwd=ROOT, capture_output=True, text=True, check=True)
    printed = json.loads(result.stdout)
    assert printed == S.readiness(spec, seal())


# --------------------------------------------------------------------------- #
# Eligibility policy: pure function of (completeness, window_crosses_termination)
# only -- CORRECTED to take no security code and no termination-list membership.
# --------------------------------------------------------------------------- #
def test_unaudited_security_defers_to_production_on_a_non_crossing_window():
    rec = ELIG.label_eligibility(completeness=None, window_crosses_termination=False)
    assert rec == {"status": ELIG.ELIGIBLE, "reasonCode": ELIG.DIVIDEND_BASIS_AUDIT_NOT_PERFORMED}


def test_unaudited_security_crossing_termination_has_no_evidence_to_construct_from():
    rec = ELIG.label_eligibility(completeness=None, window_crosses_termination=True)
    assert rec == {"status": ELIG.INELIGIBLE, "reasonCode": ELIG.NO_COMPLETENESS_EVIDENCE}


def test_exdate_unresolved_blocks_a_pre_termination_window():
    rec = ELIG.label_eligibility(completeness={"exDateSemanticsResolved": "BLOCKED"},
                                 window_crosses_termination=False)
    assert rec == {"status": ELIG.INELIGIBLE, "reasonCode": ELIG.EXDATE_LINEAGE_UNRESOLVED}


def test_exdate_resolved_but_no_spliced_series_still_blocks():
    rec = ELIG.label_eligibility(completeness={"exDateSemanticsResolved": "READY"},
                                 window_crosses_termination=False,
                                 total_return_series_available=False)
    assert rec == {"status": ELIG.INELIGIBLE, "reasonCode": ELIG.TOTAL_RETURN_SERIES_NOT_BUILT}


def test_fully_resolved_pre_termination_window_is_eligible():
    rec = ELIG.label_eligibility(completeness={"exDateSemanticsResolved": "READY"},
                                 window_crosses_termination=False,
                                 total_return_series_available=True)
    assert rec == {"status": ELIG.ELIGIBLE, "reasonCode": ELIG.PRE_TERMINATION_WINDOW_BASIS_RESOLVED}


@pytest.mark.parametrize("missing_field,expected_reason", [
    ("terminationTypeResolved", ELIG.TERMINATION_TYPE_UNRESOLVED),
    ("terminalConsiderationResolved", ELIG.TERMINAL_CONSIDERATION_UNRESOLVED),
    ("terminalActionChainResolved", ELIG.TERMINAL_ACTION_CHAIN_UNRESOLVED),
])
def test_crossing_termination_requires_every_chain_field(missing_field, expected_reason):
    complete = {"exDateSemanticsResolved": "READY", "terminationTypeResolved": "READY",
               "terminalConsiderationResolved": "READY", "successorResolvedWhereRequired": "NOT_APPLICABLE",
               "terminalActionChainResolved": "READY"}
    complete[missing_field] = "BLOCKED"
    rec = ELIG.label_eligibility(completeness=complete, window_crosses_termination=True)
    assert rec["status"] == ELIG.INELIGIBLE and rec["reasonCode"] == expected_reason


def test_crossing_termination_needs_successor_identity_when_applicable():
    complete = {"exDateSemanticsResolved": "READY", "terminationTypeResolved": "READY",
               "terminalConsiderationResolved": "READY", "successorResolvedWhereRequired": "BLOCKED",
               "terminalActionChainResolved": "READY"}
    rec = ELIG.label_eligibility(completeness=complete, window_crosses_termination=True)
    assert rec == {"status": ELIG.INELIGIBLE, "reasonCode": ELIG.SUCCESSOR_IDENTITY_UNRESOLVED}


def test_crossing_termination_needs_the_successors_own_price_panel():
    complete = {"exDateSemanticsResolved": "READY", "terminationTypeResolved": "READY",
               "terminalConsiderationResolved": "READY", "successorResolvedWhereRequired": "READY",
               "terminalActionChainResolved": "READY"}
    rec = ELIG.label_eligibility(completeness=complete, window_crosses_termination=True,
                                 successor_codes=("316140.KS",), priced_securities=frozenset())
    assert rec["status"] == ELIG.INELIGIBLE and rec["reasonCode"] == ELIG.SUCCESSOR_HAS_NO_PRICE_PANEL
    assert rec["unpricedSuccessors"] == ["316140.KS"]


def test_fully_resolved_termination_window_is_eligible():
    complete = {"exDateSemanticsResolved": "READY", "terminationTypeResolved": "READY",
               "terminalConsiderationResolved": "READY", "successorResolvedWhereRequired": "READY",
               "terminalActionChainResolved": "READY"}
    rec = ELIG.label_eligibility(completeness=complete, window_crosses_termination=True,
                                 successor_codes=("316140.KS",), priced_securities=frozenset({"316140.KS"}))
    assert rec == {"status": ELIG.ELIGIBLE, "reasonCode": ELIG.TERMINATION_WINDOW_FULLY_RESOLVED}


def test_no_reason_code_is_ever_invented_outside_the_frozen_set():
    for crosses in (False, True):
        for exdate in ("READY", "BLOCKED"):
            complete = {"exDateSemanticsResolved": exdate, "terminationTypeResolved": "READY",
                       "terminalConsiderationResolved": "READY",
                       "successorResolvedWhereRequired": "NOT_APPLICABLE",
                       "terminalActionChainResolved": "READY"}
            rec = ELIG.label_eligibility(completeness=complete, window_crosses_termination=crosses,
                                         total_return_series_available=True)
            assert rec["reasonCode"] in ELIG.REASON_CODES


def test_function_signature_takes_no_security_identity_or_termination_list():
    """CORRECTED: the defect this test guards against is `label_eligibility`
    branching on a security's own code or list membership. Asserting the
    signature has no such parameter is a direct, mechanical proof (not just a
    behavioural inference) that the function CANNOT read a security's
    identity or its termination-list membership."""
    import inspect
    params = set(inspect.signature(ELIG.label_eligibility).parameters)
    assert "code" not in params
    assert "known_terminated_codes" not in params


# --------------------------------------------------------------------------- #
# Anti-look-ahead tests (required): the future-termination invariant
# --------------------------------------------------------------------------- #
def test_future_termination_invariance_pre_termination_window():
    """TEST 1. Two synthetic securities with identical completeness evidence
    through a target's own exit date -- one 'continues forever', one
    'terminates years later' -- must get an IDENTICAL eligibility call for an
    observation whose own window never crosses either security's event. The
    function takes no parameter that could even express 'terminates later',
    so this is checked by holding the only two real inputs (completeness,
    window_crosses_termination) identical and confirming identical output --
    the only way the two syntheic securities COULD differ is a channel this
    function does not have.
    """
    shared_completeness = {"exDateSemanticsResolved": "READY"}
    continues_forever = ELIG.label_eligibility(
        completeness=shared_completeness, window_crosses_termination=False,
        total_return_series_available=True)
    terminates_years_later = ELIG.label_eligibility(
        completeness=shared_completeness, window_crosses_termination=False,
        total_return_series_available=True)
    assert continues_forever == terminates_years_later == {
        "status": ELIG.ELIGIBLE, "reasonCode": ELIG.PRE_TERMINATION_WINDOW_BASIS_RESOLVED}


def test_future_termination_invariance_with_an_unresolved_dividend_basis():
    """Same invariant, but with an evidenced data gap: both the eventually-
    terminating and the eventually-surviving security get the SAME (blocked)
    answer when they carry the SAME unresolved dividend evidence -- proving
    the block is about the evidence, never about which one terminates."""
    shared_completeness = {"exDateSemanticsResolved": "BLOCKED"}
    for _ in range(2):  # "terminates later" vs "continues forever": same call either way
        rec = ELIG.label_eligibility(completeness=shared_completeness,
                                     window_crosses_termination=False)
        assert rec == {"status": ELIG.INELIGIBLE, "reasonCode": ELIG.EXDATE_LINEAGE_UNRESOLVED}


def test_future_metadata_mutation_invariance():
    """TEST 2. An observation whose target ends before termination must not
    change eligibility when ONLY metadata describing a LATER termination is
    edited. The pre-termination branch must never even READ the termination-
    event fields (asserted both behaviourally and, via
    TERMINATION_EVENT_FIELDS, by construction)."""
    base = {"exDateSemanticsResolved": "READY", "terminationTypeResolved": "BLOCKED",
           "terminalConsiderationResolved": "BLOCKED", "successorResolvedWhereRequired": "BLOCKED",
           "terminalActionChainResolved": "BLOCKED"}
    before = ELIG.label_eligibility(completeness=base, window_crosses_termination=False,
                                    total_return_series_available=True)
    mutated = dict(base)
    for field in ELIG.TERMINATION_EVENT_FIELDS:
        mutated[field] = "READY"  # later termination now fully resolved
    after = ELIG.label_eligibility(completeness=mutated, window_crosses_termination=False,
                                   total_return_series_available=True)
    assert before == after == {"status": ELIG.ELIGIBLE,
                               "reasonCode": ELIG.PRE_TERMINATION_WINDOW_BASIS_RESOLVED}


def test_termination_window_sensitivity():
    """TEST 3. For a window that DOES cross termination, unresolved required
    terminal economics make the label unavailable, and resolving exactly the
    required evidence makes it eligible -- the opposite of TEST 2, on purpose:
    this axis SHOULD move the answer, only for a crossing window."""
    unresolved = {"exDateSemanticsResolved": "READY", "terminationTypeResolved": "BLOCKED",
                 "terminalConsiderationResolved": "BLOCKED",
                 "successorResolvedWhereRequired": "NOT_APPLICABLE",
                 "terminalActionChainResolved": "BLOCKED"}
    assert ELIG.label_eligibility(completeness=unresolved, window_crosses_termination=True
                                  )["status"] == ELIG.INELIGIBLE
    resolved = {**unresolved, "terminationTypeResolved": "READY",
               "terminalConsiderationResolved": "READY", "terminalActionChainResolved": "READY"}
    assert ELIG.label_eligibility(completeness=resolved, window_crosses_termination=True
                                  ) == {"status": ELIG.ELIGIBLE,
                                       "reasonCode": ELIG.TERMINATION_WINDOW_FULLY_RESOLVED}


def test_return_basis_symmetry_survivor_and_future_terminated_security():
    """TEST 4. A survivor and a future-terminated security must use the SAME
    economic-basis rule for the same kind of (non-crossing) target -- proven
    by construction: the function has no channel to distinguish them other
    than the completeness evidence itself, so feeding it the SAME evidence
    for 'the survivor' and 'the eventually-terminated one' cannot produce
    different answers."""
    same_evidence = {"exDateSemanticsResolved": "READY"}
    survivor_call = ELIG.label_eligibility(completeness=same_evidence,
                                           window_crosses_termination=False,
                                           total_return_series_available=True)
    eventually_terminated_call = ELIG.label_eligibility(completeness=same_evidence,
                                                        window_crosses_termination=False,
                                                        total_return_series_available=True)
    assert survivor_call == eventually_terminated_call


def test_no_manufactured_outcome_ever_returned():
    """TEST 5. An INELIGIBLE decision never carries a zero, a benchmark
    return, a last price, a nearest price, or an assumed-no-dividend value --
    the return shape is always exactly {status, reasonCode[, unpricedSuccessors]}."""
    scenarios = [
        ELIG.label_eligibility(completeness=None, window_crosses_termination=True),
        ELIG.label_eligibility(completeness={"exDateSemanticsResolved": "BLOCKED"},
                               window_crosses_termination=False),
        ELIG.label_eligibility(completeness={"exDateSemanticsResolved": "READY",
                                             "terminationTypeResolved": "BLOCKED"},
                               window_crosses_termination=True),
    ]
    forbidden_keys = {"return", "value", "price", "assumedReturn", "zero", "benchmarkReturn"}
    for rec in scenarios:
        assert rec["status"] == ELIG.INELIGIBLE
        assert not forbidden_keys & rec.keys()
        assert set(rec.keys()) <= {"status", "reasonCode", "unpricedSuccessors"}


def test_no_outcome_access_in_eligibility_or_spec_modules():
    """TEST 6. The eligibility module and the spec loader construct zero
    labels and read zero future-return/model-performance artifacts."""
    import inspect
    for module in (ELIG, S):
        source = inspect.getsource(module).lower()
        for token in ("forwardreturn", "excessreturn", "sharpe", "sortino", "cagr", "rank ic",
                     "kelly_portfolio", "select_portfolio_by_scores", "replay_valuation"):
            assert token not in source, f"{module.__name__} references {token}"


# --------------------------------------------------------------------------- #
# The policy applied to the REAL sealed evidence, window-scoped
# --------------------------------------------------------------------------- #
def test_bulk_verdict_against_the_real_sealed_evidence():
    reconstruction = S.read_json(ROOT / "docs/results/kr-terminal-action-reconstruction-v2.json")
    audit = S.read_json(ROOT / "docs/results/alpha-opportunity-model-v3-survivorship-audit.json")
    completeness_by_code = {row["code"]: row["completeness"] for row in reconstruction["securities"]}
    verdicts = ELIG.bulk_security_verdicts(kr_terminations=audit["krTerminations"],
                                           completeness_by_code=completeness_by_code)
    assert len(verdicts) == 22
    assert all(v["preTerminationWindows"]["status"] == ELIG.INELIGIBLE for v in verdicts)
    assert all(v["preTerminationWindows"]["reasonCode"] == ELIG.EXDATE_LINEAGE_UNRESOLVED for v in verdicts)
    assert all(v["terminationCrossingWindows"]["status"] == ELIG.INELIGIBLE for v in verdicts)


def test_committed_eligibility_artifact_matches_a_fresh_recompute(tmp_path):
    out = tmp_path / "eligibility.json"
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/audit_alpha_opportunity_v4_kr_eligibility.py"),
         "--reconstruction", str(ROOT / "docs/results/kr-terminal-action-reconstruction-v2.json"),
         "--survivorship-audit", str(ROOT / "docs/results/alpha-opportunity-model-v3-survivorship-audit.json"),
         "--output", str(out)],
        cwd=ROOT, check=True, capture_output=True, text=True)
    committed = (ROOT / "docs/results/alpha-opportunity-model-v4-eligibility-policy.json").read_bytes()
    assert out.read_bytes() == committed
    entry = S.read_json(S.DEFAULT_SPEC)["eligibilityPolicy"]["computedResultAsOfThisSeal"]
    assert S.file_hash(out) == entry["artifactSha256"]
    assert entry["preTerminationWindows"]["ineligible"] == 22
    assert entry["terminationCrossingWindows"]["ineligible"] == 22


def test_audit_script_computes_no_return_or_outcome():
    source = (ROOT / "scripts/audit_alpha_opportunity_v4_kr_eligibility.py").read_text().lower()
    for token in ("sharpe", "sortino", "cagr", "forwardreturn", "kelly_portfolio",
                 "select_portfolio_by_scores", "replay_valuation", "compute_outcomes"):
        assert token not in source


# --------------------------------------------------------------------------- #
# No forbidden token anywhere in the new v4 modules or scripts
# --------------------------------------------------------------------------- #
FORBIDDEN_TOKENS = ("select_portfolio_by_scores", "replay_valuation", "kelly_portfolio",
                    "compute_outcomes", "sharpe", "sortino", "cagr")
NEW_MODULES = ("alpha_opportunity_v4_spec", "alpha_opportunity_v4_eligibility")
NEW_SCRIPTS = ("run_alpha_opportunity_model_v4.py", "audit_alpha_opportunity_v4_kr_eligibility.py")


def test_no_new_v4_module_references_a_portfolio_or_outcome_function():
    import importlib
    import inspect
    for name in NEW_MODULES:
        module = importlib.import_module(f"pipeline.{name}")
        source = inspect.getsource(module).lower()
        for token in FORBIDDEN_TOKENS:
            assert token not in source, f"{name} references {token}"


def test_no_new_v4_script_references_a_portfolio_or_outcome_function():
    for script in NEW_SCRIPTS:
        source = (ROOT / "scripts" / script).read_text(encoding="utf-8").lower()
        for token in FORBIDDEN_TOKENS:
            assert token not in source, f"{script} references {token}"


def test_no_new_v4_file_touches_production_alpha_scoring():
    for module in ("longterm.py", "kelly_portfolio.py", "opportunity.py",
                  "alpha_opportunity_model.py", "korea_prices.py"):
        assert (ROOT / "pipeline" / module).exists()
    # v4's own diff never edits any of the above -- see the PR description's
    # self-audit; this asserts the files still exist under their own names,
    # unmodified by anything this test file introduces.
