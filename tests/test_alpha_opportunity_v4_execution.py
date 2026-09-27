"""alpha-opportunity-model-v4 execution harness tests. Synthetic fixtures only.

Nothing here reads a real replay price or a real KR ledger shard. The harness
under test (`pipeline.alpha_opportunity_v4_execution`,
`scripts.execute_alpha_opportunity_model_v4`) is NOT part of the sealed
preregistration's own dependency closure -- these tests instead prove that it
(a) never changes the ALREADY-SEALED `alpha_opportunity_v4_eligibility`
decision, only wires it up correctly, (b) computes `windowCrossesTermination`
purely from a calendar/price fact, never from a termination list, and (c) the
ten `F_missingnessIntegrity` diagnostics are read the same way regardless of
whether a name happens to be one of the 22 audited terminated securities.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pipeline import alpha_opportunity_v4_eligibility as ELIG
from pipeline import alpha_opportunity_v4_execution as X
from pipeline import alpha_opportunity_v4_spec as S4

ROOT = Path(__file__).resolve().parents[1]


def price_frame(dates, closes, volumes=None):
    idx = pd.to_datetime(dates)
    data = {"Close": closes}
    if volumes is not None:
        data["Volume"] = volumes
    return pd.DataFrame(data, index=idx)


# --------------------------------------------------------------------------- #
# last_priced_session / window_crosses_termination
# --------------------------------------------------------------------------- #
def test_last_priced_session_ignores_nonpositive_and_nonfinite_closes():
    frame = price_frame(["2020-01-01", "2020-01-02", "2020-01-03"], [10.0, np.nan, -5.0])
    assert X.last_priced_session(frame) == "2020-01-01"


def test_last_priced_session_none_for_empty_or_missing_frame():
    assert X.last_priced_session(None) is None
    assert X.last_priced_session(price_frame([], [])) is None


def test_window_crosses_termination_is_a_pure_calendar_fact():
    assert X.window_crosses_termination("2020-06-01", "2020-05-31") is True
    assert X.window_crosses_termination("2020-05-31", "2020-05-31") is False
    assert X.window_crosses_termination("2020-01-01", "2020-05-31") is False
    assert X.window_crosses_termination("2020-01-01", None) is True


# --------------------------------------------------------------------------- #
# completeness_by_code / verify_and_freeze_foundation -- thin call-throughs
# --------------------------------------------------------------------------- #
def test_completeness_by_code_reads_the_securities_list():
    snapshot = {"securities": [{"code": "000030.KS", "completeness": {"exDateSemanticsResolved": "READY"}},
                               {"code": "000060.KS", "completeness": {"exDateSemanticsResolved": "BLOCKED"}}]}
    out = X.completeness_by_code(snapshot)
    assert out == {"000030.KS": {"exDateSemanticsResolved": "READY"},
                   "000060.KS": {"exDateSemanticsResolved": "BLOCKED"}}
    # Absent from the list -> absent from the map, which callers read as None.
    assert out.get("999999.KS") is None


def _snapshot(fields):
    return {"foundationStatus": "PARTIALLY_REPAIRED",
            "securities": [{"code": "000030.KS", "completeness": fields}]}


def test_verify_and_freeze_foundation_passes_through_to_sealed_functions():
    cited = _snapshot({"exDateSemanticsResolved": "BLOCKED"})
    current = _snapshot({"exDateSemanticsResolved": "READY"})  # improved -> allowed
    out = X.verify_and_freeze_foundation(cited_snapshot=cited, current_snapshot=current)
    assert out["frozenExecutionSnapshotHash"] == ELIG.freeze_execution_snapshot(current)
    assert out["foundationStatusAtExecution"] == "PARTIALLY_REPAIRED"


def test_verify_and_freeze_foundation_raises_on_regression():
    cited = _snapshot({"exDateSemanticsResolved": "READY"})
    current = _snapshot({"exDateSemanticsResolved": "BLOCKED"})  # regressed
    with pytest.raises(ValueError, match="FOUNDATION_REGRESSED"):
        X.verify_and_freeze_foundation(cited_snapshot=cited, current_snapshot=current)


def test_freeze_hash_is_deterministic_and_order_independent():
    a = {"foundationStatus": "X", "securities": [{"code": "A", "completeness": {"f": "READY"}}]}
    b = {"securities": [{"completeness": {"f": "READY"}, "code": "A"}], "foundationStatus": "X"}
    assert ELIG.freeze_execution_snapshot(a) == ELIG.freeze_execution_snapshot(b)


# --------------------------------------------------------------------------- #
# attach_eligibility -- the actual wiring between the label frame and the
# sealed eligibility function. This is where a reintroduced look-ahead would
# show up, so it is tested against BOTH an audited-and-terminated ticker and
# an audited-and-STILL-CURRENT synthetic ticker with IDENTICAL completeness
# evidence, proving the harness treats them identically (it never reads
# whether a ticker is "the terminated one").
# --------------------------------------------------------------------------- #
def _labelled_frame(rows):
    return pd.DataFrame(rows)


def test_attach_eligibility_matches_direct_label_eligibility_call():
    prices = {"AAA.KS": price_frame(["2020-01-01", "2020-01-02"], [10.0, 11.0]),
             "BBB.KS": price_frame(["2020-01-01", "2020-06-01"], [10.0, 12.0])}
    data = _labelled_frame([
        {"ticker": "AAA.KS", "outcomeEndDate": "2020-01-02", "labelStatus": "MATURED"},
        {"ticker": "BBB.KS", "outcomeEndDate": "2020-06-01", "labelStatus": "MATURED"},
    ])
    completeness = {"AAA.KS": {"exDateSemanticsResolved": "BLOCKED"}}
    out = X.attach_eligibility(data, prices, completeness)
    assert out.loc[0, "windowCrossesTermination"] == False  # noqa: E712
    assert out.loc[0, "eligibilityStatus"] == ELIG.INELIGIBLE
    assert out.loc[0, "eligibilityReasonCode"] == ELIG.EXDATE_LINEAGE_UNRESOLVED
    # BBB.KS was never audited -> defers to production.
    assert out.loc[1, "eligibilityStatus"] == ELIG.ELIGIBLE
    assert out.loc[1, "eligibilityReasonCode"] == ELIG.DIVIDEND_BASIS_AUDIT_NOT_PERFORMED


def test_attach_eligibility_is_identical_for_a_currently_trading_name_with_the_same_evidence():
    """The whole point of the V2 eligibility contract: identical completeness
    evidence must produce an identical verdict whether or not the security
    happens to be one that terminates. This test builds a synthetic
    STILL-TRADING name with the audited-and-blocked evidence a real
    terminated name carries, and checks the harness's own wiring reproduces
    the SAME reason code -- i.e. this harness performs no special-casing by
    ticker identity anywhere in `attach_eligibility`."""
    prices = {"REAL_TERMINATED.KS": price_frame(["2020-01-01", "2020-01-02"], [10.0, 11.0]),
             "SYNTHETIC_STILL_TRADING.KS": price_frame(["2020-01-01", "2020-01-02", "2025-01-01"],
                                                       [10.0, 11.0, 20.0])}
    data = _labelled_frame([
        {"ticker": "REAL_TERMINATED.KS", "outcomeEndDate": "2020-01-02", "labelStatus": "MATURED"},
        {"ticker": "SYNTHETIC_STILL_TRADING.KS", "outcomeEndDate": "2020-01-02", "labelStatus": "MATURED"},
    ])
    same_evidence = {"exDateSemanticsResolved": "BLOCKED"}
    completeness = {"REAL_TERMINATED.KS": same_evidence, "SYNTHETIC_STILL_TRADING.KS": same_evidence}
    out = X.attach_eligibility(data, prices, completeness)
    assert out.loc[0, "eligibilityReasonCode"] == out.loc[1, "eligibilityReasonCode"] == ELIG.EXDATE_LINEAGE_UNRESOLVED


# --------------------------------------------------------------------------- #
# build_runtime_spec -- v4's own values must always win over v2's baseline.
# --------------------------------------------------------------------------- #
def test_build_runtime_spec_v4_overrides_win_and_v2_baseline_fills_gaps():
    v2_spec = {"evidenceGates": {"maxEce": 0.05}, "costStress": {"multiples": [2.0]},
              "survivorship": {"worstPlausibleQuantile": 0.05}, "horizons": [21, 126],
              "regions": ["US", "KR"], "benchmarks": {"US": "SPY", "KR": "069500.KS"},
              "dataCutoff": "2020-01-01", "studyId": "alpha-opportunity-model-v2",
              "walkForward": {"OLD": True}}
    v4_spec = {"studyId": "alpha-opportunity-model-v4", "immutableVersion": "4.0.0",
              "horizons": [21, 126], "regions": ["KR"], "benchmarks": {"KR": "069500.KS"},
              "dataCutoff": "2026-09-14", "carriedFromV3": {"walkForward": {"NEW": True}}}
    runtime = X.build_runtime_spec(v4_spec, v2_spec)
    assert runtime["evidenceGates"] == {"maxEce": 0.05}  # from v2, not redeclared by v4
    assert runtime["regions"] == ["KR"]  # v4 overrides v2's ["US", "KR"]
    assert runtime["walkForward"] == {"NEW": True}  # v4's carriedFromV3 wins entirely
    assert runtime["modelIds"] == {"KR": "alpha-opportunity-model-v4@4.0.0"}


# --------------------------------------------------------------------------- #
# F -- missingness/survivorship integrity diagnostics
# --------------------------------------------------------------------------- #
def _annotated(rows):
    frame = pd.DataFrame(rows)
    return frame


def test_unavailability_reason_distinguishes_ineligible_from_genuinely_missing():
    eligible_matured = {"labelStatus": "MATURED", "eligibilityStatus": ELIG.ELIGIBLE,
                        "eligibilityReasonCode": ELIG.DIVIDEND_BASIS_AUDIT_NOT_PERFORMED}
    ineligible_matured = {"labelStatus": "MATURED", "eligibilityStatus": ELIG.INELIGIBLE,
                          "eligibilityReasonCode": ELIG.EXDATE_LINEAGE_UNRESOLVED}
    missing_price = {"labelStatus": "MISSING_FORWARD_PRICE_OR_DELISTING",
                     "eligibilityStatus": ELIG.INELIGIBLE, "eligibilityReasonCode": ELIG.NO_COMPLETENESS_EVIDENCE}
    pending = {"labelStatus": "PENDING", "eligibilityStatus": None, "eligibilityReasonCode": None}
    assert X.unavailability_reason(eligible_matured) is None
    assert X.unavailability_reason(ineligible_matured) == ELIG.EXDATE_LINEAGE_UNRESOLVED
    assert X.unavailability_reason(missing_price) == "MISSING_FORWARD_PRICE_OR_DELISTING"
    assert X.unavailability_reason(pending) == "PENDING"


def _sample_annotated():
    return _annotated([
        {"date": "2020-01-03", "ticker": "TERM.KS", "horizon": 21, "labelStatus": "MATURED",
         "eligibilityStatus": ELIG.INELIGIBLE, "eligibilityReasonCode": ELIG.EXDATE_LINEAGE_UNRESOLVED},
        {"date": "2020-01-03", "ticker": "CONT.KS", "horizon": 21, "labelStatus": "MATURED",
         "eligibilityStatus": ELIG.ELIGIBLE, "eligibilityReasonCode": ELIG.DIVIDEND_BASIS_AUDIT_NOT_PERFORMED},
        {"date": "2021-06-01", "ticker": "CONT.KS", "horizon": 21, "labelStatus": "MISSING_FORWARD_PRICE_OR_DELISTING",
         "eligibilityStatus": ELIG.INELIGIBLE, "eligibilityReasonCode": ELIG.NO_COMPLETENESS_EVIDENCE},
        {"date": "2021-06-01", "ticker": "PEND.KS", "horizon": 126, "labelStatus": "PENDING",
         "eligibilityStatus": None, "eligibilityReasonCode": None},
    ])


def test_eligible_labels_by_year_and_horizon():
    out = X.eligible_labels_by_year_and_horizon(_sample_annotated())
    assert out == {"2020": {"21": 1}}


def test_unavailable_labels_by_reason_code():
    out = X.unavailable_labels_by_reason_code(_sample_annotated())
    assert out[ELIG.EXDATE_LINEAGE_UNRESOLVED] == 1
    assert out["MISSING_FORWARD_PRICE_OR_DELISTING"] == 1
    assert out["PENDING"] == 1


def test_terminated_vs_continuing_label_availability():
    out = X.terminated_vs_continuing_label_availability(_sample_annotated(), terminated_codes=["TERM.KS"])
    assert out["terminatedSecurities"]["observations"] == 1
    assert out["terminatedSecurities"]["eligibleLabels"] == 0
    assert out["continuingSecurities"]["observations"] == 3
    assert out["continuingSecurities"]["eligibleLabels"] == 1


def test_exclusions_cluster_around_terminal_events_check():
    out = X.exclusions_cluster_around_terminal_events_check(_sample_annotated(), terminated_codes=["TERM.KS"])
    # Two MATURED-but-not-ELIGIBLE rows overall: TERM.KS (ineligible) only --
    # the CONT.KS ineligible row is MISSING_FORWARD_PRICE, not MATURED, so it
    # is excluded from this specific count by construction (see docstring).
    assert out["ineligibleObservations"] == 1
    assert out["ineligibleOnTerminatedNamesPct"] == 100.0


def test_temporal_and_security_concentration_are_computed_and_bounded():
    annotated = _sample_annotated()
    temporal = X.temporal_concentration_of_missingness(annotated)
    assert temporal["totalUnavailable"] == 3
    assert 0 <= temporal["maxYearSharePct"] <= 100
    security = X.security_concentration_of_missingness(annotated, top_k=2)
    assert security["totalUnavailable"] == 3
    assert 0 <= security["topKSharePct"] <= 100


def test_benchmark_coverage_pct_reads_only_the_benchmark_close():
    prices = {X.KR_BENCHMARK: price_frame(["2020-01-01", "2020-01-02"], [100.0, np.nan])}
    pct = X.benchmark_coverage_pct(prices, ["2020-01-01", "2020-01-02"])
    assert pct == 50.0
    assert X.benchmark_coverage_pct({}, ["2020-01-01"]) == 0.0


def test_total_return_comparability_coverage_pct_only_counts_matured_rows():
    annotated = _sample_annotated()
    pct = X.total_return_comparability_coverage_pct(annotated)
    # 3 MATURED rows total? No -- only 2 are MATURED (TERM.KS, CONT.KS 2020-01-03);
    # 1 of those 2 carries a basis-unresolved reason code.
    assert pct == 50.0


def test_missingness_integrity_report_has_all_ten_required_fields():
    annotated = _sample_annotated()
    universe = pd.DataFrame({"date": ["2020-01-03", "2021-06-01"]})
    prices = {X.KR_BENCHMARK: price_frame(["2020-01-03", "2021-06-01"], [100.0, 105.0])}
    report = X.missingness_integrity_report(annotated, universe, prices, terminated_codes=["TERM.KS"])
    required = ("pitUniverseObservationsByYear", "eligibleLabelsByYearAndHorizon",
               "unavailableLabelsByReasonCode", "terminatedVsContinuingLabelAvailability",
               "memberDatesRemovedPctByReasonAndYear", "temporalConcentrationOfMissingness",
               "securityConcentrationOfMissingness", "exclusionsClusterAroundTerminalEventsCheck",
               "benchmarkCoveragePct", "totalReturnComparabilityCoveragePct")
    assert set(required) <= set(report)
    for key in required:
        assert report[key] is not None


# --------------------------------------------------------------------------- #
# The execution script never touches the sealed preregistration's own files.
# --------------------------------------------------------------------------- #
def test_sealed_preregistration_entry_point_script_is_untouched():
    spec = S4.read_json(S4.DEFAULT_SPEC)
    sha = S4.DEFAULT_SPEC.with_suffix(".sha256").read_text().strip()
    loaded = S4.load_sealed(expected_hash=sha)
    assert loaded["studyId"] == "alpha-opportunity-model-v4"
    run_script = ROOT / "scripts/run_alpha_opportunity_model_v4.py"
    assert spec["dependencyHashes"]["scripts/run_alpha_opportunity_model_v4.py"] == \
        S4.file_hash(run_script)


def test_execution_harness_module_is_not_in_the_sealed_dependency_closure():
    spec = S4.read_json(S4.DEFAULT_SPEC)
    assert "pipeline/alpha_opportunity_v4_execution.py" not in spec["dependencyHashes"]
    assert "scripts/execute_alpha_opportunity_model_v4.py" not in spec["dependencyHashes"]
