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

import gzip
import json
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd
import pytest

from pipeline import alpha_opportunity_spec as S1
from pipeline import alpha_opportunity_v2_evaluation as E
from pipeline import alpha_opportunity_v2_model as M
from pipeline import alpha_opportunity_v4_eligibility as ELIG
from pipeline import alpha_opportunity_v4_execution as X
from pipeline import alpha_opportunity_v4_spec as S4
from pipeline import regional_alpha_features as SOURCES
from pipeline import replay_calendar as RC
from scripts import execute_alpha_opportunity_model_v4 as CLI
from scripts import run_alpha_opportunity_model_v2 as V2CLI

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


# =========================================================================== #
# Regression tests for the V1 harness's sequencing defect. The V1 harness
# built forward labels (`target_from_sessions`) and called `label_eligibility`
# for every horizon BEFORE the coverage gate; every test below would have
# failed against it.
# =========================================================================== #
PRICE_FEATURES = ["relative126", "acceleration21", "vol63", "logVolumeShock60",
                  "shockPersistence5d", "volumePriceAlignment"]
ACCOUNTING_FEATURES = ["ocfToNetIncomePct", "assetGrowthPct", "debtGrowthPct"]
TICKERS = [f"T{i:02d}.KS" for i in range(12)]


class OutcomeTouched(AssertionError):
    pass


def _runtime():
    v4 = S4.read_json(S4.DEFAULT_SPEC)
    v2 = S1.read_json(ROOT / "research_specs/alpha-opportunity-model-v2.json")
    return X.build_runtime_spec(v4, v2)


def _registry():
    return S1.read_json(ROOT / "research_specs/alpha-opportunity-model-v1-features.json")


def _synthetic(start, end, *, accounting=lambda year: True, unpriced_year=None):
    """A PIT feature frame plus sealed-shaped price panels. Every name trades
    every KR session (so it is tradable), except that in `unpriced_year` ten of
    the twelve names have no close at all -- which makes that region-year
    unvouched above v2's 20% tolerance."""
    sessions = RC.sessions("2014-06-01", end, "KR")
    prices = {}
    for i, ticker in enumerate(TICKERS + [X.KR_BENCHMARK]):
        frame = pd.DataFrame({"Close": 100.0, "Volume": 1000.0}, index=sessions)
        if unpriced_year and i < 10:
            frame = frame.loc[frame.index.year != int(unpriced_year)]
        prices[ticker] = frame
    rows = []
    for date in SOURCES.weekly_grid(start, end, "KR"):
        has_accounting = accounting(date[:4])
        for ticker in TICKERS:
            rows.append({"date": date, "region": "KR", "ticker": ticker,
                         **{f: 1.0 for f in PRICE_FEATURES},
                         **{f: (1.0 if has_accounting else np.nan) for f in ACCOUNTING_FEATURES}})
    return pd.DataFrame(rows), prices


def _forbid_outcomes(monkeypatch):
    """Every function that reads a forward price, builds or consumes a label,
    or calls the v4 observation-eligibility policy raises on touch."""
    def boom(name):
        def _raise(*a, **k):
            raise OutcomeTouched(name)
        return _raise
    for module, name in ((E, "target_from_sessions"), (E, "attach_labels"), (E, "net_label"),
                         (E, "evaluate_cell"), (M, "predict_cell"), (M, "fit_heads"),
                         (ELIG, "label_eligibility"), (X, "attach_eligibility"),
                         (X, "last_priced_session"), (X, "window_crosses_termination"),
                         (X, "missingness_integrity_report")):
        monkeypatch.setattr(module, name, boom(f"{module.__name__}.{name}"))


def _run(frame, prices, **kw):
    return CLI.run_from_features(frame, prices, runtime_spec=_runtime(), registry=_registry(),
                                 completeness_map={}, terminated_codes=[], spec_hash="0" * 64, **kw)


def test_A_B_C_coverage_failure_touches_no_outcome_and_no_eligibility(monkeypatch):
    frame, prices = _synthetic("2016-01-01", "2016-12-31", accounting=lambda year: False)
    _forbid_outcomes(monkeypatch)
    result = _run(frame, prices, stop_before_labels=False)
    assert result["status"] == "BLOCKED_BY_DATA_INTEGRITY"
    assert result["stoppedBeforeLabels"] is True
    assert {c["feature"] for c in result["detail"]["coverageFailures"]} == set(ACCOUNTING_FEATURES)
    assert result["counts"] == {"targetFromSessionsCalls": 0, "labelEligibilityCalls": 0,
                                "predictCellCalls": 0, "evaluateCellCalls": 0}


def test_coverage_failure_blocks_even_without_the_stop_flag_and_before_the_identity_recheck(monkeypatch):
    frame, prices = _synthetic("2016-01-01", "2016-12-31", accounting=lambda year: False)
    _forbid_outcomes(monkeypatch)
    hook_calls = []
    result = _run(frame, prices, stop_before_labels=False, before_labels=lambda: hook_calls.append(1))
    assert result["stoppedBeforeLabels"] is True and hook_calls == []


def test_D_region_year_eligibility_runs_before_coverage_and_restricts_its_denominator(monkeypatch):
    frame, prices = _synthetic("2016-01-01", "2021-12-31", unpriced_year="2019",
                               accounting=lambda year: year != "2019")
    order = []
    real_eligibility, real_gates = V2CLI.eligibility, V2CLI.pre_label_gates

    def eligibility(frame, spec):
        order.append("eligibility")
        return real_eligibility(frame, spec)

    def gates(frame, registry, spec):
        order.append("gates")
        assert "eligibleRegionYear" in frame
        return real_gates(frame, registry, spec)
    monkeypatch.setattr(V2CLI, "eligibility", eligibility)
    monkeypatch.setattr(V2CLI, "pre_label_gates", gates)
    _forbid_outcomes(monkeypatch)
    result = _run(frame, prices, stop_before_labels=True)
    assert order == ["eligibility", "gates"]
    by_year = {r["year"]: r for r in result["regionYearEligibility"]}
    assert by_year["2019"]["eligible"] is False and by_year["2019"]["unvouchedPct"] > 20.0
    assert all(by_year[y]["eligible"] for y in ("2016", "2017", "2018", "2020", "2021"))
    # 2019's accounting is entirely missing, so the gate passes ONLY because
    # 2019 is outside the eligible denominator, exactly as v2 specifies.
    assert result["status"] == CLI.STOPPED_FOR_REVIEW
    assert not any(c["year"] == "2019" for c in result["coverage"])


def test_D_counterfactual_without_region_year_eligibility_the_same_frame_fails_coverage():
    frame, prices = _synthetic("2016-01-01", "2021-12-31", unpriced_year="2019",
                               accounting=lambda year: year != "2019")
    guard = V2CLI.tradability_frame(prices, frame, "KR", 20)
    merged = frame.merge(guard, on=["date", "region", "ticker"])
    merged["eligibleRegionYear"] = True
    with pytest.raises(V2CLI.PreLabelStop) as stop:
        V2CLI.pre_label_gates(merged, _registry(), _runtime())
    assert {c["year"] for c in stop.value.detail["coverageFailures"]} == {"2019"}


def test_gates_passing_with_stop_before_labels_constructs_no_label(monkeypatch):
    frame, prices = _synthetic("2016-01-01", "2021-12-31")
    _forbid_outcomes(monkeypatch)
    result = _run(frame, prices, stop_before_labels=True)
    assert result["status"] == CLI.STOPPED_FOR_REVIEW and result["stoppedBeforeLabels"] is True
    assert result["counts"]["targetFromSessionsCalls"] == 0


def test_labels_come_strictly_after_gates_and_after_the_identity_recheck(monkeypatch):
    frame, prices = _synthetic("2016-01-01", "2021-12-31")
    order = []
    monkeypatch.setattr(V2CLI, "pre_label_gates",
                        lambda *a, _g=V2CLI.pre_label_gates: (order.append("gates"), _g(*a))[1])

    def target(*a, **k):
        order.append("target")
        raise OutcomeTouched("target_from_sessions")
    monkeypatch.setattr(E, "target_from_sessions", target)
    with pytest.raises(OutcomeTouched):
        _run(frame, prices, stop_before_labels=False, before_labels=lambda: order.append("recheck"))
    assert order == ["gates", "recheck", "target"]


def test_F_a_failing_identity_recheck_blocks_every_label(monkeypatch):
    frame, prices = _synthetic("2016-01-01", "2021-12-31")
    _forbid_outcomes(monkeypatch)

    def changed():
        raise ValueError("INPUT_IDENTITY_CHANGED_MID_RUN")
    with pytest.raises(ValueError, match="INPUT_IDENTITY_CHANGED_MID_RUN"):
        _run(frame, prices, stop_before_labels=False, before_labels=changed)


# --------------------------------------------------------------------------- #
# Input identity (F) and the moving-branch guard (E)
# --------------------------------------------------------------------------- #
def _fixture_inputs(root: Path):
    files = {"ledger/fundamentals/kr/dart-2015.jsonl.gz": gzip.compress(b'{"a":1}\n', mtime=0),
             "ledger/fundamentals/kr/shares.jsonl.gz": gzip.compress(b'{"s":1}\n', mtime=0),
             "ledger/universe/kr/krx-universe-2013.jsonl.gz": gzip.compress(b'{"u":1}\n', mtime=0)}
    for rel, data in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(data)
    body = {"replayVersion": "replay-v16", "components": {}}
    manifest = {**body, "sha256": S1.digest(body)}
    (root / X.REPLAY_MANIFEST).parent.mkdir(parents=True, exist_ok=True)
    (root / X.REPLAY_MANIFEST).write_text(json.dumps(manifest))
    rels = list(files) + [X.REPLAY_MANIFEST]
    return {"signalHistoryCommit": "sealed", "replayManifestSha256": manifest["sha256"],
            "gitBlobSha1": {rel: X.git_blob_sha1(root / rel) for rel in rels}}


def test_F_unchanged_inputs_verify_and_bookkeeping_is_outside_the_identity(tmp_path):
    sealed = _fixture_inputs(tmp_path)
    (tmp_path / "ledger/fundamentals/kr/manifest.json").write_text("{}")
    (tmp_path / "ledger/fundamentals/kr/absent.json").write_text("{}")
    identity = X.verify_input_identity(sealed, tmp_path)
    assert identity["gitBlobSha1"] == sealed["gitBlobSha1"]
    assert identity["signalHistoryCommit"] is None


@pytest.mark.parametrize("mutate,code", [
    (lambda r: (r / "ledger/fundamentals/kr/dart-2015.jsonl.gz").write_bytes(b"x"), "INPUT_SNAPSHOT_CHANGED"),
    (lambda r: (r / "ledger/fundamentals/kr/shares.jsonl.gz").unlink(), "INPUT_SNAPSHOT_CHANGED"),
    (lambda r: (r / "ledger/universe/kr/krx-universe-2013.jsonl.gz").write_bytes(b"x"), "INPUT_SNAPSHOT_CHANGED"),
    (lambda r: (r / "ledger/fundamentals/kr/dart-2099.jsonl.gz").write_bytes(b"x"), "UNSEALED_RAW_SHARD"),
    (lambda r: (r / "ledger/universe/kr/krx-universe-2099.jsonl.gz").write_bytes(b"x"), "UNSEALED_RAW_SHARD"),
    (lambda r: (r / X.REPLAY_MANIFEST).write_text("{}"), "INPUT_SNAPSHOT_CHANGED"),
])
def test_F_any_input_mutation_is_rejected(tmp_path, mutate, code):
    sealed = _fixture_inputs(tmp_path)
    mutate(tmp_path)
    with pytest.raises(ValueError, match=code):
        X.verify_input_identity(sealed, tmp_path)


def test_F_manifest_digest_is_checked_against_the_sealed_value(tmp_path):
    sealed = _fixture_inputs(tmp_path)
    sealed = {**sealed, "replayManifestSha256": "0" * 64}
    with pytest.raises(ValueError, match="REPLAY_MANIFEST_CHANGED"):
        X.verify_input_identity(sealed, tmp_path)


def test_F_identity_is_checked_before_any_row_is_read(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise OutcomeTouched("data read before identity")
    monkeypatch.setattr(SOURCES, "load_inputs", boom)
    monkeypatch.setattr(X, "load_kr_raw", boom)
    monkeypatch.setattr(X, "load_kr_memberships", boom)
    v4 = S4.read_json(S4.DEFAULT_SPEC)
    with pytest.raises(ValueError, match="INPUT_SNAPSHOT_CHANGED|REPLAY_MANIFEST"):
        CLI.execute(v4, {}, S1.read_json(CLI.V3_SPEC), input_root=tmp_path,
                    output=tmp_path / "out", stop_before_labels=True)


def _git_repo(root: Path):
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    for key, value in (("user.email", "t@t"), ("user.name", "t")):
        subprocess.run(["git", "-C", str(root), "config", key, value], check=True)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "x"], check=True)
    return subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()


def test_E_a_moved_checkout_cannot_pass_as_the_frozen_commit(tmp_path):
    sealed = _fixture_inputs(tmp_path)
    frozen = _git_repo(tmp_path)
    assert X.verify_input_identity(sealed, tmp_path, expected_signal_history_sha=frozen)["signalHistoryCommit"] == frozen
    (tmp_path / "ledger/fundamentals/kr/manifest.json").write_text("{}")  # bookkeeping only
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-q", "-m", "branch moved"], check=True)
    with pytest.raises(ValueError, match="SIGNAL_HISTORY_COMMIT_MISMATCH"):
        X.verify_input_identity(sealed, tmp_path, expected_signal_history_sha=frozen)


def _workflow_jobs(text):
    """{job: its YAML text}. Plain-text split on the two top-level job keys
    this workflow has; the repository carries no YAML parser dependency."""
    body = text[text.index("\njobs:\n"):]
    execute_at = body.index("\n  execute:\n")
    return {"freeze": body[:execute_at], "execute": body[execute_at:]}


def _checkout_refs(job_text):
    return [line.split("ref:", 1)[1].strip() for line in job_text.splitlines()
            if line.strip().startswith("ref:")]


def test_E_workflow_never_checks_out_signal_history_by_branch_name():
    text = (ROOT / ".github/workflows/alpha-opportunity-model-v4-execution.yml").read_text()
    jobs = _workflow_jobs(text)
    assert _checkout_refs(jobs["freeze"]) == ["${{ env.SEALED_SIGNAL_HISTORY_COMMIT }}"]
    assert _checkout_refs(jobs["execute"]) == ["${{ needs.freeze.outputs.signal_history_sha }}"]
    sealed = S1.read_json(CLI.V3_SPEC)["futureExecutionInputs"]["signalHistoryCommit"]
    assert f"SEALED_SIGNAL_HISTORY_COMMIT: {sealed}" in text
    assert "--expected-signal-history-sha" in jobs["execute"]
    assert "--expected-input-identity-sha256" in jobs["execute"]
    assert not any("signal-history" in ref for ref in _checkout_refs(text))


def test_sealed_input_identity_names_every_raw_file_the_harness_reads():
    sealed = X.sealed_input_identity(S1.read_json(CLI.V3_SPEC))
    blobs = sealed["gitBlobSha1"]
    assert sealed["signalHistoryCommit"] == "4ea107ed0cde289f0a049a65ff13d2441a786710"
    assert sealed["replayManifestSha256"] == "f0781292f508a123c234ded6d28aa8e84a0dc3cc29500e14989dc0b68f53b4d2"
    assert {f"ledger/fundamentals/kr/dart-{y}.jsonl.gz" for y in range(2015, 2027)} <= set(blobs)
    assert {f"ledger/universe/kr/krx-universe-{y}.jsonl.gz" for y in range(2013, 2027)} <= set(blobs)
    assert "ledger/fundamentals/kr/shares.jsonl.gz" in blobs and X.REPLAY_MANIFEST in blobs
    assert not any("/us/" in r or r.endswith("manifest.json") for r in blobs)
    assert len(blobs) == 28


# --------------------------------------------------------------------------- #
# G -- every sealed spec and sidecar is byte-identical
# --------------------------------------------------------------------------- #
def test_G_sealed_specs_and_sidecars_are_unchanged():
    expected = {"alpha-opportunity-model-v1": "e3c699b197fd558506d7157fa6dd8cdb91156faccd0e6e9547d21d5baa23dd6e",
                "alpha-opportunity-model-v2": "97c3727b37eeab71e31ffee17a2f81cac29f0333552ff04a5374ef48484b0e19",
                "alpha-opportunity-model-v3": "f6e11fafc2d46137d3f8385858c58d9991cb3809a2f811c368a81baf149fc3fe",
                "alpha-opportunity-model-v4": "4db0a96267a8b0de41c445ac600a8064a760191abdd29d97600153a78cbab8e6"}
    for study, sha in expected.items():
        path = ROOT / "research_specs" / f"{study}.json"
        assert S1.digest(S1.read_json(path)) == sha
        assert path.with_suffix(".sha256").read_text().strip() == sha
    S4.load_sealed(expected_hash=expected["alpha-opportunity-model-v4"])
    CLI.S2.load_sealed(ROOT / "research_specs/alpha-opportunity-model-v2.json",
                       expected_hash=expected["alpha-opportunity-model-v2"])
