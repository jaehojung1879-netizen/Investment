"""Tests of the SUPPLEMENTAL, descriptive diagnostic layer of the v5 execution harness. SYNTHETIC FIXTURES ONLY.

No real price, ledger row, label or Alpha outcome is read and nothing here executes the frozen v5 protocol. What is
proved: the diagnostics cannot change the primary result, they are exact where they claim to be, they read only what
the registered information rules allow, and the multiple-testing firewall holds.
"""
from __future__ import annotations

import copy
import gzip
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import v5_harness_fixtures as W  # noqa: E402

from pipeline import alpha_opportunity_model as V1  # noqa: E402
from pipeline import alpha_opportunity_v5_diagnostics as D  # noqa: E402
from pipeline import alpha_opportunity_v5_execution as X  # noqa: E402
from pipeline.alpha_opportunity_spec import digest  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DIAG_PATH = ROOT / "research_specs/alpha-opportunity-model-v5-diagnostics-v1.json"
spec = W.sealed_spec()
diag = W.diagnostic_spec()
HARNESS = {"synthetic": "harness-hash"}
CUTOFF = "2019-12-27"     # a shorter synthetic calendar keeps the suite fast; the mechanics are identical


def supplemental(capture, primary_sha, rt=None):
    return D.run_supplemental(capture, runtime_spec=rt or W.runtime(CUTOFF), diag=diag, diag_sha=W.DIAG_SHA,
                              primary_sha=primary_sha, harness_hashes=HARNESS)


@pytest.fixture(scope="module")
def leaky():
    """A complete synthetic primary run with its in-memory intermediates, and the diagnostics built once from them."""
    world = W.make_world(seed=7, n=12, leak=True, cutoff=CUTOFF)
    capture = {}
    result = X.run_execution(**W.run_kwargs(world), capture=capture)
    frozen = X.freeze_primary(result)
    out = supplemental(capture, frozen["sha256"])
    return {"world": world, "capture": capture, "result": result, "frozen": frozen, "out": out}


def replay_primary(leaky, monkeypatch):
    """Route `execute_with_diagnostics` through the real orchestration using the already-computed primary run, so the
    isolation tests do not pay for the primary computation again."""
    def fake(**kwargs):
        capture = kwargs.pop("capture", None)
        if capture is not None:
            capture.update(leaky["capture"])
        return copy.deepcopy(leaky["result"])
    monkeypatch.setattr(X, "run_execution", fake)


def artifact(out, key):
    return out["artifacts"][D.ARTIFACTS[key]]


def models(out):
    return json.loads(artifact(out, "models"))["horizons"]


def summary(out):
    return json.loads(artifact(out, "summary"))["horizons"]


def ledger(out):
    return [json.loads(line) for line in gzip.decompress(artifact(out, "ledger")).splitlines()]


# --------------------------------------------------------------------------- #
# The frozen diagnostic spec
# --------------------------------------------------------------------------- #
def test_diagnostic_spec_is_frozen_sealed_and_states_the_firewall():
    assert (ROOT / "research_specs/alpha-opportunity-model-v5-diagnostics-v1.sha256").read_text().strip() == W.DIAG_SHA
    assert digest(json.loads(DIAG_PATH.read_text())) == W.DIAG_SHA
    firewall = diag["firewall"]
    for key in D.REQUIRED_FALSE:
        assert firewall[key] is False, key
    assert firewall["allDiagnosticsAreDescriptiveExploratory"] is True and firewall["noPValueOrSignificanceMining"] is True
    assert "NEW preregistered" in firewall["futurePromotionOfAnyFindingRequires"]
    assert diag["parent"]["specSha256"] == W.SPEC_SHA == D.PARENT_SPEC_SHA256
    assert "not a v5.1" in diag["parent"]["relationship"] or "NOT_AMENDMENT" in diag["parent"]["relationship"]


def test_a_changed_or_unpinned_diagnostic_spec_is_refused(tmp_path):
    copy_path = tmp_path / DIAG_PATH.name
    copy_path.write_bytes(DIAG_PATH.read_bytes())
    (tmp_path / "alpha-opportunity-model-v5-diagnostics-v1.sha256").write_text(W.DIAG_SHA)
    assert D.load_diagnostic_spec(copy_path, expected_hash=W.DIAG_SHA)["studyId"] == D.STUDY
    with pytest.raises(ValueError, match="SEALED_DIAGNOSTIC_SPEC_CHANGED"):
        D.load_diagnostic_spec(DIAG_PATH, expected_hash="0" * 64)
    data = json.loads(copy_path.read_text())
    data["firewall"]["resultCanRescuePrimary"] = True
    copy_path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="SEALED_DIAGNOSTIC_SPEC_CHANGED"):
        D.load_diagnostic_spec(copy_path, expected_hash=W.DIAG_SHA)


def test_a_flag_flipped_and_resealed_is_still_refused(tmp_path):
    data = json.loads(DIAG_PATH.read_text())
    data["firewall"]["modelSelectionAllowed"] = True
    path = tmp_path / DIAG_PATH.name
    path.write_text(json.dumps(data))
    resealed = digest(data)
    path.with_suffix(".sha256").write_text(resealed)
    with pytest.raises(ValueError, match="DIAGNOSTIC_FIREWALL_FLAG_NOT_FALSE"):
        D.load_diagnostic_spec(path, expected_hash=resealed)


def test_frozen_feature_groups_cover_every_active_feature_exactly_once():
    rt = W.runtime()
    for horizon in ("21", "126"):
        names = rt["allowedFeatures"]["KR"][horizon]
        groups = D.groups_for(diag, horizon)
        D.assert_groups_cover(names, groups)
        assert sorted(f for feats in groups.values() for f in feats) == sorted(names)
        assert all(D.family_of(n, groups) in D.FAMILIES for n in names)
    assert D.groups_for(diag, 126)["ACCOUNTING"] == ["assetGrowthPct", "debtGrowthPct"]
    assert diag["featureGroups"]["TREND_MOMENTUM"] == ["relative126", "acceleration21"]
    assert diag["featureGroups"]["RISK_VOLATILITY"] == ["vol63"]
    assert diag["featureGroups"]["ATTENTION_LIQUIDITY"] == ["logVolumeShock60", "shockPersistence5d", "volumePriceAlignment"]
    with pytest.raises(ValueError, match="COVER"):
        D.assert_groups_cover(["a", "b"], {"X": ["a"]})
    with pytest.raises(ValueError, match="COVER"):
        D.assert_groups_cover(["a", "b"], {"X": ["a", "b"], "Y": ["b"]})
    with pytest.raises(ValueError, match="COVER"):
        D.assert_groups_cover(["a"], {"X": ["a", "ghost"]})


def test_h21_accounting_group_is_not_applicable(leaky):
    assert "ACCOUNTING" not in D.groups_for(diag, 21) and "ACCOUNTING" in D.groups_for(diag, 126)
    assert summary(leaky["out"])["21"]["accountingGroup"] == D.NOT_APPLICABLE
    assert "B4_MINUS_GROUP_ACCOUNTING" not in models(leaky["out"])["21"]["ablations"]
    assert "B4_MINUS_GROUP_ACCOUNTING" in models(leaky["out"])["126"]["ablations"]


def test_frozen_features_and_primary_registry_are_untouched_by_the_groups():
    rt = X.build_runtime_spec(spec)
    assert rt["allowedFeatures"]["KR"]["126"] == ["relative126", "acceleration21", "vol63", "logVolumeShock60",
                                                   "shockPersistence5d", "volumePriceAlignment", "assetGrowthPct",
                                                   "debtGrowthPct"]
    assert X.rung_names(rt, 126)["B4"] == rt["allowedFeatures"]["KR"]["126"]


# --------------------------------------------------------------------------- #
# Primary result isolation
# --------------------------------------------------------------------------- #
def test_primary_result_is_identical_with_diagnostics_on_and_off(leaky):
    world = leaky["world"]
    off = D.execute_with_diagnostics(run_kwargs=W.run_kwargs(world), diag=None)
    on = D.execute_with_diagnostics(run_kwargs=W.run_kwargs(world), diag=diag, diag_sha=W.DIAG_SHA, harness_hashes=HARNESS)
    assert off["diagnosticStatus"] == "DISABLED" and on["diagnosticStatus"] == D.COMPLETE
    assert off["frozen"]["sha256"] == on["frozen"]["sha256"] == leaky["frozen"]["sha256"]
    assert off["frozen"]["payload"] == on["frozen"]["payload"]
    assert on["primaryBytes"] == off["primaryBytes"] == X.finalize(leaky["result"])     # byte-for-byte, references or not
    doc = json.loads(on["primaryBytes"])
    assert "diagnosticReferences" not in doc and doc["resultDigests"]["substantiveResultSha256"] == on["frozen"]["sha256"]
    assert on["references"]["primaryResultSha256"] == on["frozen"]["sha256"]           # the references point AT the primary
    assert on["references"]["primaryResultFileSha256"] == hashlib.sha256(on["primaryBytes"]).hexdigest()
    assert doc["overallStatus"] == json.loads(off["primaryBytes"])["overallStatus"] and doc["claims"] == json.loads(off["primaryBytes"])["claims"]


def test_primary_bytes_without_references_are_exactly_the_original_primary_serialization(leaky):
    assert X.finalize_primary(leaky["frozen"]) == X.finalize(leaky["result"])
    assert b"diagnosticReferences" not in X.finalize_primary(leaky["frozen"])


def test_a_raising_diagnostic_leaves_the_primary_status_payload_and_hash_unchanged(leaky, monkeypatch):
    replay_primary(leaky, monkeypatch)
    clean = D.execute_with_diagnostics(run_kwargs={}, diag=None)

    def boom(*a, **k):
        raise RuntimeError("diagnostic exploded")

    monkeypatch.setattr(D, "run_supplemental", boom)
    failed = D.execute_with_diagnostics(run_kwargs={"runtime_spec": W.runtime()}, diag=diag, diag_sha=W.DIAG_SHA,
                                        harness_hashes=HARNESS)
    doc = json.loads(failed["primaryBytes"])
    assert failed["diagnosticStatus"] == D.DIAGNOSTIC_ERROR and failed["diagnosticArtifacts"] == {}
    assert failed["references"]["status"] == D.DIAGNOSTIC_ERROR and failed["references"]["error"]["code"] == "RuntimeError"
    assert "diagnosticReferences" not in doc and failed["primaryBytes"] == clean["primaryBytes"]
    assert failed["frozen"]["payload"] == clean["frozen"]["payload"] and failed["frozen"]["sha256"] == clean["frozen"]["sha256"]
    clean_doc = json.loads(clean["primaryBytes"])
    assert doc["overallStatus"] == clean_doc["overallStatus"] and doc["claims"] == clean_doc["claims"]
    assert doc["overallStatus"] in ("PASS", "FAIL", "INCONCLUSIVE", "DATA_INSUFFICIENT")     # never DIAGNOSTIC_ERROR
    assert doc["substantiveResult"] is True and doc["cells"] == clean_doc["cells"]


def test_a_garbage_returning_or_mutating_diagnostic_cannot_touch_the_primary(leaky, monkeypatch):
    replay_primary(leaky, monkeypatch)
    clean = D.execute_with_diagnostics(run_kwargs={}, diag=None)
    for garbage in (None, "garbage", {"status": "PASS"}, {"status": D.COMPLETE, "artifacts": {"x": "not bytes"},
                                                           "references": {}}, 42):
        monkeypatch.setattr(D, "run_supplemental", lambda *a, _g=garbage, **k: _g)
        out = D.execute_with_diagnostics(run_kwargs={"runtime_spec": W.runtime()}, diag=diag, diag_sha=W.DIAG_SHA,
                                         harness_hashes=HARNESS)
        assert out["diagnosticStatus"] == D.DIAGNOSTIC_ERROR
        assert out["frozen"]["sha256"] == clean["frozen"]["sha256"]
        assert json.loads(out["primaryBytes"])["overallStatus"] == json.loads(clean["primaryBytes"])["overallStatus"]
        assert json.loads(out["primaryBytes"])["claims"] == json.loads(clean["primaryBytes"])["claims"]
        assert out["references"]["error"]["code"] == "DiagnosticFailure"


def test_a_diagnostic_error_authorizes_no_retry_and_changes_nothing_primary():
    out = D.run_diagnostics_safely({}, runtime_spec=W.runtime(), diag=diag, diag_sha=W.DIAG_SHA, primary_sha="0" * 64,
                                   harness_hashes=HARNESS)
    assert out["status"] == D.DIAGNOSTIC_ERROR and out["authorizesRetry"] is False and out["changesPrimary"] is False
    assert out["artifacts"] == {}


def test_the_frozen_primary_payload_is_an_independent_copy_and_tamper_is_detected(leaky):
    frozen = copy.deepcopy(leaky["frozen"])
    leaky["result"]["overallStatus"], original = "FAIL", leaky["result"]["overallStatus"]
    try:
        assert X.finalize_primary(leaky["frozen"]) == X.finalize_primary(frozen)   # later mutation of `result` is invisible
    finally:
        leaky["result"]["overallStatus"] = original
    frozen["payload"]["overallStatus"] = "FAIL"
    with pytest.raises(X.OrderingViolation, match="PRIMARY_RESULT_CHANGED_AFTER_FREEZE"):
        X.finalize_primary(frozen)


def test_diagnostics_receive_copies_and_do_not_mutate_the_primary_intermediates(leaky):
    capture = leaky["capture"]
    before = {h: (c["table"].copy(), c["cell"]["predictions"].copy(), c["modelling"].copy()) for h, c in capture["horizons"].items()}
    copied = D.copy_context(capture)
    copied["horizons"][21]["table"]["pB4"] = 1e9
    supplemental(capture, leaky["frozen"]["sha256"])
    for h, (table, predictions, modelling) in before.items():
        pd.testing.assert_frame_equal(capture["horizons"][h]["table"], table)
        pd.testing.assert_frame_equal(capture["horizons"][h]["cell"]["predictions"], predictions)
        pd.testing.assert_frame_equal(capture["horizons"][h]["modelling"], modelling)


def test_diagnostics_use_their_own_counters_and_never_the_primary_ones(leaky):
    assert leaky["out"]["counters"]["diagnosticFits"] > 0
    assert leaky["result"]["ordering"]["counters"] == json.loads(X.finalize(leaky["result"]))["ordering"]["counters"]
    assert set(leaky["result"]["ordering"]["counters"]) == set(X.Counters.NAMES)


def test_diagnostics_are_not_run_when_the_primary_did_not_reach_evaluation(monkeypatch):
    spy_calls = []
    monkeypatch.setattr(D, "run_supplemental", lambda *a, **k: spy_calls.append(1))
    world = W.make_world(seed=5, n=12)
    out = D.execute_with_diagnostics(run_kwargs=W.run_kwargs(world, mode=X.GATES_ONLY), diag=diag, diag_sha=W.DIAG_SHA,
                                     harness_hashes=HARNESS)
    assert spy_calls == [] and out["diagnosticStatus"] == D.NOT_RUN and out["diagnosticArtifacts"] == {}
    stopped = D.execute_with_diagnostics(run_kwargs=W.run_kwargs(world, rt=W.runtime(depth={"21": 30, "126": 10_000})),
                                         diag=diag, diag_sha=W.DIAG_SHA, harness_hashes=HARNESS)
    assert spy_calls == [] and stopped["diagnosticStatus"] == D.NOT_RUN
    assert json.loads(stopped["primaryBytes"])["overallStatus"] == "DATA_INSUFFICIENT"


# --------------------------------------------------------------------------- #
# Exact Ridge decomposition
# --------------------------------------------------------------------------- #
def synthetic_fold(seed=0, missing=True):
    rng = np.random.default_rng(seed)
    names = ["relative126", "acceleration21", "vol63", "logVolumeShock60"]

    def frame(dates, base, per=12):
        rows = []
        for d in dates:
            for i in range(per):
                row = {"date": d, "region": "KR", "ticker": f"T{i:02d}", **{n: float(rng.normal()) for n in names}}
                rows.append(row)
        df = pd.DataFrame(rows)
        df["forwardRelativeReturn"] = 0.02 * df.acceleration21 - 0.01 * df.vol63 + rng.normal(0, 0.02, len(df))
        df["beatBenchmark"] = (df.forwardRelativeReturn > 0).astype(int)
        df["outcomeEndDate"] = base
        return df

    train = frame([f"2015-{m:02d}-{d:02d}" for m in range(1, 7) for d in (5, 12, 19, 26)], "2015-12-15")
    valid = frame(["2016-01-08", "2016-01-15", "2016-01-22"], "2016-03-01")
    if missing:
        train.loc[train.index[::7], "relative126"] = np.nan
        valid.loc[valid.index[::5], "relative126"] = np.nan
        valid.loc[valid.index[::9], "vol63"] = np.nan
    return train, valid, names


def test_exact_ridge_reconstruction_including_the_missing_indicator_terms():
    train, valid, names = synthetic_fold()
    fitted = X.fit_model("ridge", train, valid, names, W.runtime())
    view = D.linear_view(fitted, valid)
    assert np.max(np.abs(view["score"] - fitted.prediction)) < 1e-12
    assert D.assert_exact_reconstruction(view, fitted.prediction, 1e-9, "test") < 1e-12
    assert np.allclose(view["intercept"] + view["contribution"].sum(axis=1), fitted.prediction, rtol=0, atol=1e-12)
    j = view["active"].index("relative126")
    assert np.any(view["missingIndicator"][:, j] == 1) and np.any(view["missingPart"][:, j] != 0)
    assert np.allclose(view["contribution"], view["valuePart"] + view["missingPart"])
    assert np.allclose(view["valuePart"], view["transformed"] * view["valueCoefficient"])
    assert np.allclose(view["missingPart"], view["missingIndicator"] * view["missingCoefficient"])
    with pytest.raises(D.DiagnosticFailure, match="EXACT_DECOMPOSITION_FAILED"):
        D.assert_exact_reconstruction(view, fitted.prediction + 1e-3, 1e-9, "tampered")


def test_reconstruction_holds_on_every_evaluated_row_of_the_full_synthetic_run(leaky):
    for horizon, doc in models(leaky["out"]).items():
        assert doc["folds"] and all(f["maxExactReconstructionGap"] < 1e-9 for f in doc["folds"]), horizon
    rows = ledger(leaky["out"])
    assert rows
    for row in rows[:: max(1, len(rows) // 400)]:
        total = row["b4Intercept"] + sum(row["b4FeatureContributions"].values())
        assert total == pytest.approx(row["predictions"]["B4"], abs=1e-9)
        for family, entry in row["b4FamilyContributions"].items():
            assert entry["absolute"] >= abs(entry["signed"]) - 1e-15


def test_a_refit_that_differs_from_the_primary_prediction_is_a_diagnostic_error(leaky, monkeypatch):
    real = X.fit_model

    def perturbed(kind, *a, **k):
        fitted = real(kind, *a, **k)
        if kind == "ridge" and len(a[2]) > 1:
            fitted.prediction = fitted.prediction + 1e-6
        return fitted

    monkeypatch.setattr(X, "fit_model", perturbed)
    out = D.run_diagnostics_safely(leaky["capture"], runtime_spec=W.runtime(), diag=diag, diag_sha=W.DIAG_SHA,
                                   primary_sha=leaky["frozen"]["sha256"], harness_hashes=HARNESS)
    assert out["status"] == D.DIAGNOSTIC_ERROR and "DIFFERS_FROM_PRIMARY" in out["error"]["message"]


def test_logistic_decomposition_is_on_the_log_odds_scale_only():
    train, valid, names = synthetic_fold()
    fitted = X.fit_model("logistic", train, valid, names, W.runtime())
    view = D.linear_view(fitted, valid)
    logit = fitted.estimator.decision_function(fitted.transformer.transform(valid))
    assert np.max(np.abs(view["score"] - logit)) < 1e-9
    assert not np.allclose(view["score"], fitted.prediction)          # the score is NOT the probability
    assert np.allclose(1.0 / (1.0 + np.exp(-view["score"])), fitted.prediction, atol=1e-12)


def test_logistic_records_are_labelled_log_odds_in_the_artifact(leaky):
    for doc in models(leaky["out"]).values():
        assert doc["logisticCoefficientRecords"] and all(r["scale"] == "LOG_ODDS" for r in doc["logisticCoefficientRecords"])
    text = artifact(leaky["out"], "summary").decode() + artifact(leaky["out"], "models").decode()
    assert "probabilityContribution" not in text and "probabilityScaleAdditiv" not in text


# --------------------------------------------------------------------------- #
# Coefficient stability, contributions
# --------------------------------------------------------------------------- #
def test_coefficient_stability_summaries_are_descriptive_and_correct():
    records = [{"refitYear": y, "standardizedValueCoefficient": {"a": v, "b": 0.5},
                "missingIndicatorCoefficient": {"a": 0.0, "b": 0.0}} for y, v in
               zip((2016, 2017, 2018, 2019, 2020), (0.3, 0.1, -0.2, -0.1, 0.4))]
    out = D.coefficient_stability(records, ["a", "b"])
    a = out["features"]["a"]["value"]
    assert a["median"] == pytest.approx(0.1) and a["medianAbsolute"] == pytest.approx(0.2)
    assert a["fractionPositive"] == pytest.approx(3 / 5) and a["fractionNegative"] == pytest.approx(2 / 5)
    assert a["signFlipCount"] == 2 and a["signByRefit"] == [1, 1, -1, -1, 1]
    assert a["yearToYearDrift"] == pytest.approx([-0.2, -0.3, 0.1, 0.5])
    assert out["features"]["b"]["value"]["signFlipCount"] == 0
    assert out["l2CoefficientVectorDrift"][0] == {"fromYear": 2016, "toYear": 2017, "l2": pytest.approx(0.2)}
    assert "significan" not in json.dumps(out).lower()


def test_an_omitted_feature_contributes_zero_to_the_l2_drift_and_is_counted_omitted():
    records = [{"refitYear": 2016, "standardizedValueCoefficient": {"a": 1.0}, "missingIndicatorCoefficient": {"a": 0.0}},
               {"refitYear": 2017, "standardizedValueCoefficient": {}, "missingIndicatorCoefficient": {}}]
    out = D.coefficient_stability(records, ["a"])
    assert out["features"]["a"]["value"]["omitted"] == 1 and out["l2CoefficientVectorDrift"][0]["l2"] == pytest.approx(1.0)


def test_contribution_summaries_have_shares_that_sum_to_one_per_date(leaky):
    for horizon, block in summary(leaky["out"]).items():
        contributions = block["contributions"]
        assert contributions["byDate"]
        for entry in contributions["byDate"]:
            shares = [f["shareOfAbsoluteContribution"] for f in entry["families"].values()]
            if all(s is not None for s in shares):
                assert sum(shares) == pytest.approx(1.0)
            for f in entry["families"].values():
                assert f["meanAbsolute"] >= abs(f["meanSigned"]) - 1e-15 and f["crossSectionalDispersion"] >= 0
        assert set(contributions["overall"]) == set(D.groups_for(diag, horizon))
        assert "model attribution" in contributions["definitions"]["note"]


# --------------------------------------------------------------------------- #
# Leave-one-feature / leave-one-family-out
# --------------------------------------------------------------------------- #
def test_ablations_use_identical_folds_and_training_frames_and_no_selection(leaky, monkeypatch):
    seen = []
    real = X.fit_model

    def spy(kind, train, valid, names, spec_):
        seen.append({"kind": kind, "names": tuple(names), "train": (tuple(map(str, train.date.unique()[:3])), len(train),
                                                                    str(train.outcomeEndDate.max())),
                     "valid": (str(valid.date.min()), len(valid))})
        return real(kind, train, valid, names, spec_)

    monkeypatch.setattr(X, "fit_model", spy)
    hctx = copy.deepcopy(leaky["capture"]["horizons"][126])
    hctx.update(schedule=leaky["capture"]["schedule"], diagnosticCounters={"diagnosticFits": 0, "aleFeatureFolds": 0})
    out = D.run_horizon(126, hctx, W.runtime(), diag)
    by_fold = {}
    for fit in seen:
        by_fold.setdefault(fit["valid"], set()).add(fit["train"])
    assert by_fold and all(len(v) == 1 for v in by_fold.values())        # one training frame per fold, for every model
    names = hctx["rungs"]["B4"]
    ridge_sets = {f["names"] for f in seen if f["kind"] == "ridge"}
    expected = {tuple(names)} | {tuple(n for n in names if n != j) for j in names} | \
        {tuple(n for n in names if n not in members) for members in D.groups_for(diag, 126).values()}
    assert ridge_sets == expected
    assert set(out["ablations"]) == set(D.ablation_sets(names, D.groups_for(diag, 126)))
    fold_years = {f["refitYear"] for f in out["folds"]}
    assert fold_years == set(D.evaluation_folds(hctx["cell"]))         # exactly the primary's evaluation folds


def test_ablation_deltas_are_descriptive_signed_and_carry_per_fold_values(leaky):
    block = models(leaky["out"])["126"]["ablations"]
    group = block["B4_MINUS_GROUP_TREND_MOMENTUM"]
    assert group["status"] == "MEASURED" and set(group["overall"]) >= {"pooledMse", "equalDateMse", "rankWeightedSpread",
                                                                       "predictionCrossSectionalVariance"}
    assert group["byFold"] and all("pooledMse" in v for v in group["byFold"].values())
    assert group["overall"]["pooledMse"] > 0        # removing the leaky family hurts B4 in this synthetic world
    assert models(leaky["out"])["126"]["attributionMap"]["acceleration21"]["family"] == "TREND_MOMENTUM"
    text = artifact(leaky["out"], "models").decode().lower()
    assert "significant" not in text and "winner" not in text and '"pass"' not in text and '"fail"' not in text


def test_ablation_metric_definitions_on_a_known_frame():
    frame = pd.DataFrame({"date": ["d1"] * 3 + ["d2"] * 3, "ticker": list("abc") * 2, "foldYear": 2016,
                          "forwardRelativeReturn": [2.0, 1.0, 0.0, 2.0, 1.0, 0.0],
                          "pB4": [2.0, 1.0, 0.0, 2.0, 1.0, 0.0], "pAbl": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0]})
    out = D.ablation_deltas(frame, "pB4", "pAbl")["overall"]
    assert out["pooledMse"] == pytest.approx(2 / 3) and out["equalDateMse"] == pytest.approx(2 / 3)
    assert out["predictionCrossSectionalVariance"] == pytest.approx(-2 / 3)
    assert out["rankWeightedSpread"] < 0          # the ablation's constant prediction ranks by ticker, not by outcome


def test_ablating_a_group_that_leaves_no_features_is_not_applicable_not_an_error():
    sets = D.ablation_sets(["a"], {"ONLY": ["a"]})
    assert sets == {"B4_MINUS_FEATURE_a": ["a"], "B4_MINUS_GROUP_ONLY": ["a"]}


def test_b4_predictions_are_untouched_by_the_ablation_fits(leaky):
    table = leaky["capture"]["horizons"][126]["table"]
    ledger_b4 = {(r["signalDate"], r["ticker"]): r["predictions"]["B4"] for r in ledger(leaky["out"]) if r["horizon"] == 126}
    assert len(ledger_b4) == len(table)
    for date, ticker, p in zip(table.date, table.ticker, table.pB4):
        assert ledger_b4[(date, ticker)] == pytest.approx(p, abs=1e-15)


# --------------------------------------------------------------------------- #
# Redundancy: training data only
# --------------------------------------------------------------------------- #
def test_association_reads_training_rows_only_and_matches_a_manual_weighted_correlation():
    train, valid, names = synthetic_fold(missing=False)
    fitted = X.fit_model("ridge", train, valid, names, W.runtime())
    out = D.training_association(train, names, fitted.transformer)
    key = "relative126|acceleration21"
    weights = V1.date_weights(train.date)
    raw = fitted.transformer.raw(train)
    expected = D.weighted_pearson(raw[:, 0], raw[:, 1], weights)
    assert out[key]["pearson"] == pytest.approx(expected) and out[key]["pairs"] == len(train)
    import inspect
    assert "valid" not in inspect.signature(D.training_association).parameters
    assert D.training_association(train, names, fitted.transformer) == out
    with pytest.raises(TypeError):
        D.training_association(train, names, fitted.transformer, valid)  # type: ignore[call-arg]


def test_association_fold_inputs_precede_every_validation_row(leaky, monkeypatch):
    calls = []
    real = D.training_association

    def spy(train, names, transformer):
        calls.append(pd.to_datetime(train.outcomeEndDate).max())
        return real(train, names, transformer)

    monkeypatch.setattr(D, "training_association", spy)
    hctx = copy.deepcopy(leaky["capture"]["horizons"][21])
    hctx.update(schedule=leaky["capture"]["schedule"], diagnosticCounters={"diagnosticFits": 0, "aleFeatureFolds": 0})
    out = D.run_horizon(21, hctx, W.runtime(), diag)
    firsts = sorted(pd.Timestamp(f["trainingCutoff"]) for f in out["folds"])
    assert len(calls) == len(firsts) and all(c < f for c, f in zip(sorted(calls), firsts))


def test_association_weights_dates_equally_and_pearson_spearman_are_defined_and_aggregated():
    agg = D.aggregate_association([{"a|b": {"pearson": 0.2, "spearman": 0.3, "pairs": 5}},
                                   {"a|b": {"pearson": 0.6, "spearman": 0.1, "pairs": 5}},
                                   {"a|b": {"pearson": None, "spearman": None, "pairs": 0}}])
    assert agg["a|b"]["pearson"]["median"] == pytest.approx(0.4) and agg["a|b"]["folds"] == 3
    assert D.weighted_pearson(np.array([1.0, 2, 3]), np.array([1.0, 2, 3]), np.ones(3)) == pytest.approx(1.0)
    assert D.weighted_pearson(np.array([1.0, 1, 1]), np.array([1.0, 2, 3]), np.ones(3)) is None


def test_the_attribution_map_places_unique_group_and_shared_information_side_by_side(leaky):
    amap = models(leaky["out"])["126"]["attributionMap"]
    for name, row in amap.items():
        assert set(row) == {"family", "uniquePooledMseDelta", "familyPooledMseDelta", "mostAssociatedFeature"}
        assert "verdict" not in row and "redundant" not in json.dumps(row).lower()


# --------------------------------------------------------------------------- #
# Linear versus nonlinear, head concordance
# --------------------------------------------------------------------------- #
def frame_with(pb4, pb5, prob=None, y=None, dates=6, names=10):
    rows = []
    rng = np.random.default_rng(3)
    for d in range(dates):
        for i in range(names):
            rows.append({"date": f"2020-01-{d + 1:02d}", "ticker": f"T{i:02d}", "foldYear": 2020,
                         "forwardRelativeReturn": float(rng.normal()) if y is None else y(d, i),
                         "beatBenchmarkNet": int(rng.random() > 0.5), "pB4": pb4(d, i), "pB5": pb5(d, i),
                         "prob": np.nan if prob is None else prob(d, i), "pB0": 0.0, "pB1": 0.0, "pB2": 0.0})
    return pd.DataFrame(rows)


def test_linear_vs_nonlinear_reads_identity_as_full_agreement():
    frame = frame_with(lambda d, i: i - 4.5, lambda d, i: i - 4.5)
    out = D.linear_vs_nonlinear(frame)["overall"]
    assert out["equalDateSpearmanMean"] == pytest.approx(1.0) and out["pooledPearson"] == pytest.approx(1.0)
    assert out["topQuintileOverlapMean"] == 1.0 and out["bottomQuintileOverlapMean"] == 1.0
    assert out["signDisagreementRate"] == 0.0 and out["dispersionOfB5MinusB4Pooled"] == pytest.approx(0.0)
    assert out["mseB5MinusB4"] == pytest.approx(0.0)


def test_linear_vs_nonlinear_reads_reversal_as_full_disagreement_and_is_unavailable_without_b5():
    frame = frame_with(lambda d, i: i - 4.5, lambda d, i: 4.5 - i)
    out = D.linear_vs_nonlinear(frame)["overall"]
    assert out["equalDateSpearmanMean"] == pytest.approx(-1.0) and out["topQuintileOverlapMean"] == 0.0
    assert out["signDisagreementRate"] == 1.0 and D.linear_vs_nonlinear(frame)["byFold"]["2020"]["signalWeeks"] == 6
    assert D.linear_vs_nonlinear(frame.assign(pB5=np.nan))["status"] == "UNAVAILABLE"


def test_head_concordance_counts_disagreements_and_never_gates():
    frame = frame_with(lambda d, i: i - 4.5, lambda d, i: 0.0, prob=lambda d, i: 0.9 - 0.1 * i)
    out = D.head_concordance(frame)
    assert out["role"] == "DESCRIPTIVE_ONLY_NEVER_A_GATE" and out["equalDateSpearmanOfHeadsMean"] == pytest.approx(-1.0)
    positive_low_prob = sum(1 for _ in range(6) for i in range(10) if i - 4.5 > 0 and 0.9 - 0.1 * i < 0.5)
    non_positive_high_prob = sum(1 for _ in range(6) for i in range(10) if i - 4.5 <= 0 and 0.9 - 0.1 * i >= 0.5)
    assert out["disagreement"]["expectedReturnPositiveProbabilityBelowHalf"] == positive_low_prob
    assert out["disagreement"]["expectedReturnNotPositiveProbabilityAtLeastHalf"] == non_positive_high_prob
    assert [d["decile"] for d in out["expectedReturnDeciles"]] == list(range(1, 11))
    assert sum(d["rows"] for d in out["expectedReturnDeciles"]) == len(frame)
    assert sum(b["rows"] for b in out["probabilityCalibration"]) == len(frame)
    assert D.head_concordance(frame.assign(prob=np.nan))["status"] == "UNAVAILABLE"


# --------------------------------------------------------------------------- #
# ALE
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def hgb_fold():
    rng = np.random.default_rng(4)
    names = ["relative126", "acceleration21", "vol63", "logVolumeShock60"]

    def frame(n_dates, first, outcome_end):
        rows = [{"date": f"{first}-{d + 1:02d}", "region": "KR", "ticker": f"T{i:02d}", "outcomeEndDate": outcome_end,
                 **{n: float(rng.normal()) for n in names}} for d in range(n_dates) for i in range(30)]
        df = pd.DataFrame(rows)
        df["forwardRelativeReturn"] = 0.05 * np.tanh(df.acceleration21 * 2) + rng.normal(0, 0.01, len(df))
        df["beatBenchmark"] = (df.forwardRelativeReturn > 0).astype(int)
        return df

    train, valid = frame(20, "2015-06", "2015-12-15"), frame(20, "2016-01", "2016-03-01")
    fitted = X.fit_model("hgb", train, valid, names, W.runtime())
    return train, valid, fitted, names


def test_ale_bin_edges_come_from_training_data_only(hgb_fold):
    train, valid, fitted, _ = hgb_fold
    base = D.ale_feature(fitted, train, valid, "acceleration21", bins=10, minimum_support=5)
    shifted = valid.copy()
    shifted["acceleration21"] = shifted["acceleration21"] * 5 + 3          # a very different evaluation distribution
    other = D.ale_feature(fitted, train, shifted, "acceleration21", bins=10, minimum_support=5)
    assert base["edges"] == other["edges"] and len(base["edges"]) == 11
    expected = np.unique(np.quantile(train.acceleration21.to_numpy(float), np.linspace(0, 1, 11)))
    assert np.allclose(base["edges"], expected)
    retrained = train.copy()
    retrained["acceleration21"] = retrained["acceleration21"] * 2
    changed = D.ale_feature(fitted, retrained, valid, "acceleration21", bins=10, minimum_support=5)
    assert changed["edges"] != base["edges"]


def test_unsupported_ale_bins_are_reported_and_never_extrapolated(hgb_fold):
    train, valid, fitted, _ = hgb_fold
    narrow = valid.copy()
    edges = np.unique(np.quantile(train.acceleration21.to_numpy(float), np.linspace(0, 1, 11)))
    narrow["acceleration21"] = np.linspace(edges[4] + 1e-6, edges[5] - 1e-6, len(narrow))   # every row inside bin 5
    out = D.ale_feature(fitted, train, narrow, "acceleration21", bins=10, minimum_support=50)
    statuses = [b["status"] for b in out["bins"]]
    assert statuses.count("SUPPORTED") == 1 and statuses[4] == "SUPPORTED"
    for k, b in enumerate(out["bins"]):
        if b["status"] == "UNSUPPORTED":
            assert b["localEffect"] is None and b["accumulated"] is None and b["centeredAle"] is None
            assert b["support"] < 50
    assert all(b["accumulated"] is None for b in out["bins"][5:])            # nothing accumulated across a gap


def test_a_fully_supported_ale_curve_is_centered_and_descriptive(hgb_fold):
    train, valid, fitted, _ = hgb_fold
    out = D.ale_feature(fitted, train, valid, "acceleration21", bins=10, minimum_support=5)
    bins = out["bins"]
    assert out["supportedBins"] == len(bins) and all(b["centeredAle"] is not None for b in bins)
    lower = [0.0] + [b["accumulated"] for b in bins[:-1]]
    support = np.array([b["support"] for b in bins], dtype=float)
    centre = float(np.sum(support * (np.array(lower) + np.array([b["accumulated"] for b in bins])) / 2) / support.sum())
    assert all(b["centeredAle"] == pytest.approx(b["accumulated"] - centre) for b in bins)
    midpoints = np.array([(lo - centre + b["centeredAle"]) / 2 for lo, b in zip(lower, bins)])
    assert float(np.sum(support * midpoints) / support.sum()) == pytest.approx(0.0, abs=1e-12)   # count-weighted mean is zero
    assert bins[-1]["centeredAle"] > bins[0]["centeredAle"]           # the synthetic surface is increasing in the feature


def test_ale_runs_in_the_full_synthetic_run_with_support_recorded_in_every_bin(leaky):
    ale = models(leaky["out"])["126"]["ale"]
    assert set(ale) == set(leaky["capture"]["horizons"][126]["rungs"]["B4"])
    for feature, block in ale.items():
        for fold in block["perFold"]:
            if fold["status"] == "MEASURED":
                assert all("support" in b and b["status"] in ("SUPPORTED", "UNSUPPORTED") for b in fold["bins"])
        assert block["aggregate"]


# --------------------------------------------------------------------------- #
# Regimes
# --------------------------------------------------------------------------- #
def benchmark_path(n=900, seed=2, shock_at=None):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2013-01-02", periods=n)
    r = rng.normal(0.0004, 0.008, n)
    if shock_at is not None:
        r[shock_at:] = rng.normal(-0.02, 0.06, n - shock_at)
    return days, 100 * np.cumprod(1 + r)


def test_regime_labels_use_only_the_past_and_a_future_shock_cannot_alter_them():
    days, close = benchmark_path()
    schedule = [str(d.date()) for d in days[::5]]
    base = D.benchmark_regimes(close, days, schedule, diag["regimes"])
    cut = 600
    days2, shocked = benchmark_path(shock_at=cut)
    assert np.array_equal(close[:cut], shocked[:cut])
    future = D.benchmark_regimes(shocked, days, schedule, diag["regimes"])
    unchanged = [d for d in schedule if pd.Timestamp(d) < days[cut]]
    assert unchanged and all(future[d] == base[d] for d in unchanged)
    assert any(future[d] != base[d] for d in schedule if pd.Timestamp(d) >= days[cut])   # the shock is real


def test_regime_volatility_threshold_is_the_expanding_median_of_strictly_earlier_dates():
    days, close = benchmark_path()
    schedule = [str(d.date()) for d in days[::5]]
    out = D.benchmark_regimes(close, days, schedule, diag["regimes"])
    minimum = diag["regimes"]["VOLATILITY"]["minimumPriorSignalDates"]
    vols = [out[d]["volatility63"] for d in schedule]
    first_defined = next(i for i, v in enumerate(vols) if v is not None)
    for i, d in enumerate(schedule):
        prior = [v for v in vols[:i] if v is not None]
        if out[d]["volatility63"] is None or len(prior) < minimum:
            assert out[d]["volatility"] is None and out[d]["regime"] == "UNDETERMINED"
        else:
            expected = "HIGH" if out[d]["volatility63"] > np.median(prior) else "LOW"
            assert out[d]["volatility"] == expected
    assert first_defined > 0 and diag["regimes"]["VOLATILITY"]["threshold"].startswith("median of the same statistic over the STRICTLY EARLIER")


def test_regime_trend_is_the_sign_of_the_trailing_126_session_return():
    days = pd.bdate_range("2013-01-02", periods=400)
    up = 100 * np.cumprod(np.full(400, 1.001))
    down = 100 * np.cumprod(np.full(400, 0.999))
    schedule = [str(days[300].date())]
    assert D.benchmark_regimes(up, days, schedule, diag["regimes"])[schedule[0]]["trend"] == "POSITIVE"
    assert D.benchmark_regimes(down, days, schedule, diag["regimes"])[schedule[0]]["trend"] == "NON_POSITIVE"
    assert D.benchmark_regimes(up, days, [str(days[50].date())], diag["regimes"])[str(days[50].date())]["trend"] is None


def test_regime_tables_mark_thin_cells_sparse_and_report_by_year_without_winners(leaky):
    block = summary(leaky["out"])["21"]["regimes"]
    assert block["minimumSignalWeeks"] == 26 and set(block["byRegime"]) == set(D.REGIMES)
    for cell in list(block["byRegime"].values()) + list(block["byCalendarYear"].values()):
        if cell["status"] == D.SPARSE:
            assert set(cell) == {"status", "signalWeeks", "eligibleNames"} and cell["signalWeeks"] < 26
        else:
            assert cell["signalWeeks"] >= 26 and {"b4Mse", "b0Mse", "b2Mse", "rankWeightedSpread"} <= set(cell)
    assert block["byCalendarYear"] and block["notAClaim"] is True
    assert not any(k in json.dumps(block).lower() for k in ("winner", "loser", "best", "worst"))


def test_regime_cells_below_the_minimum_report_counts_only():
    frame = frame_with(lambda d, i: i - 4.5, lambda d, i: i - 4.5, dates=5)
    regimes = {d: {"regime": "POSITIVE/LOW"} for d in frame.date.unique()}
    out = D.regime_tables(frame, regimes, diag["regimes"])
    assert out["byRegime"]["POSITIVE/LOW"] == {"status": D.SPARSE, "signalWeeks": 5, "eligibleNames": 50}
    assert out["byRegime"]["POSITIVE/HIGH"]["signalWeeks"] == 0


# --------------------------------------------------------------------------- #
# Artifacts: determinism, ledger, hashes, firewall
# --------------------------------------------------------------------------- #
def test_diagnostic_artifacts_are_deterministic(leaky):
    again = supplemental(leaky["capture"], leaky["frozen"]["sha256"])
    assert again["artifacts"] == leaky["out"]["artifacts"] and again["references"] == leaky["out"]["references"]


def test_ledger_serialization_is_row_order_invariant_and_byte_deterministic():
    rows = [{"horizon": h, "signalDate": d, "ticker": t, "v": i} for i, (h, d, t) in
            enumerate([(126, "2020-01-03", "B"), (21, "2020-01-10", "A"), (21, "2020-01-03", "B"), (21, "2020-01-03", "A")])]
    first = D.serialize_ledger(rows)
    assert first == D.serialize_ledger(list(reversed(rows))) == D.serialize_ledger(rows)
    lines = gzip.decompress(first).splitlines()
    assert [json.loads(line)["ticker"] for line in lines] == ["A", "B", "A", "B"]
    assert first[4:8] == b"\x00\x00\x00\x00"                        # gzip header mtime is fixed at 0


def test_the_ledger_is_input_row_order_invariant_end_to_end(leaky):
    world = leaky["world"]
    capture = {}
    result = X.run_execution(**W.run_kwargs(world, shuffle=True), capture=capture)
    frozen = X.freeze_primary(result)
    assert frozen["sha256"] == leaky["frozen"]["sha256"]
    out = supplemental(capture, frozen["sha256"])
    assert artifact(out, "ledger") == artifact(leaky["out"], "ledger")
    assert artifact(out, "models") == artifact(leaky["out"], "models") and artifact(out, "summary") == artifact(leaky["out"], "summary")


def test_the_ledger_carries_the_registered_fields_for_every_primary_evaluation_row(leaky):
    rows = ledger(leaky["out"])
    tables = leaky["capture"]["horizons"]
    assert len(rows) == sum(len(t["table"]) for t in tables.values())
    fields = set(diag["ledger"]["fields"])
    for row in rows[:50]:
        assert fields <= set(row) and row["studyId"] == D.STUDY and row["eligibilityStatus"] == "ELIGIBLE"
        assert set(row["predictions"]) == {"B0", "B1", "B2", "B3", "B4", "B5"} and row["regime"] in D.REGIMES + ("UNDETERMINED",)
        assert set(row["transformedFeatureValues"]) == set(row["missingIndicators"]) <= set(row["featureValues"])
    assert [r["horizon"] for r in rows] == sorted(r["horizon"] for r in rows)
    keys = [(r["horizon"], r["signalDate"], r["ticker"]) for r in rows]
    assert keys == sorted(keys) and len(keys) == len(set(keys))
    assert not any("sourceDocument" in r or "rawFiling" in r for r in rows[:50])
    h21 = next(r for r in rows if r["horizon"] == 21)
    assert "ACCOUNTING" not in h21["b4FamilyContributions"] and set(h21["b4FamilyContributions"]) == {"TREND_MOMENTUM", "RISK_VOLATILITY", "ATTENTION_LIQUIDITY"}


def test_every_artifact_carries_its_hashes_schema_and_row_count_and_the_primary_references_them(leaky, monkeypatch):
    replay_primary(leaky, monkeypatch)
    out = D.execute_with_diagnostics(run_kwargs={"runtime_spec": W.runtime()}, diag=diag, diag_sha=W.DIAG_SHA,
                                     harness_hashes=HARNESS)
    doc = json.loads(out["primaryBytes"])
    refs = out["references"]
    assert json.loads(out["referencesBytes"]) == refs and "diagnosticReferences" not in doc
    assert refs["status"] == D.COMPLETE and refs["diagnosticSpecSha256"] == W.DIAG_SHA
    assert refs["primaryResultSha256"] == doc["resultDigests"]["substantiveResultSha256"]
    assert set(refs["artifacts"]) == set(D.ARTIFACTS.values())
    for name, data in out["diagnosticArtifacts"].items():
        assert refs["artifacts"][name]["sha256"] == hashlib.sha256(data).hexdigest() and refs["artifacts"][name]["bytes"] == len(data)
        assert refs["artifacts"][name]["schemaVersion"] == D.SCHEMA_VERSION
    ledger_rows = ledger({"artifacts": out["diagnosticArtifacts"]})
    assert refs["artifacts"][D.ARTIFACTS["ledger"]]["rowCount"] == len(ledger_rows)
    for key in ("models", "summary"):
        header = json.loads(out["diagnosticArtifacts"][D.ARTIFACTS[key]])
        assert header["schemaVersion"] == D.SCHEMA_VERSION and header["primaryResultSha256"] == refs["primaryResultSha256"]
        assert header["diagnosticSpecSha256"] == W.DIAG_SHA and header["harnessFileHashes"] == HARNESS
        assert header["affectsPrimaryClaim"] is False and header["promotionEligible"] is False and header["rowCount"] >= 1
    assert out["primaryBytes"] == X.finalize_primary(out["frozen"])            # the primary never embeds the references


def test_the_multiple_testing_firewall_refuses_significance_winner_and_promotion_keys():
    for key in ("significantFeature", "pValue", "p_value", "winnerModel", "bestFeature", "promotedPredictor",
                "tStat", "holmAdjusted", "bonferroniAlpha"):
        with pytest.raises(D.DiagnosticFailure, match="FIREWALL"):
            D.assert_firewall({"a": [{"nested": {key: 1}}]}, diag)
    D.assert_firewall({"promotionEligible": False, "affectsPrimaryClaim": False, "medianCoefficient": 0.1}, diag)


def test_real_artifacts_contain_no_forbidden_key_anywhere(leaky):
    D.assert_firewall(json.loads(artifact(leaky["out"], "models")), diag)
    D.assert_firewall(json.loads(artifact(leaky["out"], "summary")), diag)
    for row in ledger(leaky["out"])[:20]:
        D.assert_firewall(row, diag)


def test_an_injected_forbidden_key_makes_the_supplemental_run_a_diagnostic_error(leaky, monkeypatch):
    real = D.contribution_summaries
    monkeypatch.setattr(D, "contribution_summaries", lambda *a, **k: {**real(*a, **k), "significantFeature": "x"})
    out = D.run_diagnostics_safely(leaky["capture"], runtime_spec=W.runtime(), diag=diag, diag_sha=W.DIAG_SHA,
                                   primary_sha=leaky["frozen"]["sha256"], harness_hashes=HARNESS)
    assert out["status"] == D.DIAGNOSTIC_ERROR and "FIREWALL" in out["error"]["message"]


# --------------------------------------------------------------------------- #
# The state of the repository
# --------------------------------------------------------------------------- #
def test_no_authorization_no_result_and_no_formal_execution_exist():
    assert not list((ROOT / "docs/results").glob("alpha-opportunity-model-v5*"))
    assert not list(ROOT.glob("**/alpha-opportunity-model-v5-result*"))
    assert not list(ROOT.glob("**/alpha-opportunity-model-v5-diagnostic-ledger*"))
    assert spec["executionHarness"]["status"] == "NOT_BUILT_IN_THIS_PR"     # the frozen, unedited statement


def test_diagnostic_module_is_in_the_pinned_harness_files_and_outside_the_sealed_closure():
    from pipeline import alpha_opportunity_v5_spec as S5
    assert "pipeline/alpha_opportunity_v5_diagnostics.py" in X.HARNESS_FILES
    assert "pipeline/alpha_opportunity_v5_diagnostics.py" not in S5.sealed_file_set(spec)
    assert (ROOT / "research_specs/alpha-opportunity-model-v5-diagnostics-v1.json").exists()
    assert "research_specs/alpha-opportunity-model-v5-diagnostics-v1.json" not in spec["dependencyHashes"]


def test_no_primary_module_imports_the_diagnostics_and_the_diagnostics_have_no_search_path():
    for rel in ("pipeline/alpha_opportunity_v5_evidence.py", "pipeline/alpha_opportunity_v5_execution.py"):
        code = (ROOT / rel).read_text()
        assert "alpha_opportunity_v5_diagnostics" not in code.replace("alpha_opportunity_v5_diagnostics.py\"", ""), rel
    text = (ROOT / "pipeline/alpha_opportunity_v5_diagnostics.py").read_text()
    for forbidden in ("GridSearchCV", "RandomizedSearchCV", "cross_val", "optuna", "import shap"):
        assert forbidden not in text


def test_workflow_pins_the_diagnostic_spec_and_uploads_diagnostics_separately_from_the_result():
    import re
    text = (ROOT / ".github/workflows/alpha-opportunity-model-v5-execution.yml").read_text()
    assert re.search(r"DIAGNOSTICS_SHA256: ([0-9a-f]{64})", text).group(1) == W.DIAG_SHA
    assert "alpha-opportunity-model-v5-diagnostics-v1.sha256" in text
    assert text.count("--diagnostic-sha256") == 2                       # gates-only and execute
    assert "name: alpha-opportunity-model-v5-diagnostics\n" in text and "name: alpha-opportunity-model-v5-result\n" in text
    assert "v5-result/alpha-opportunity-model-v5-result.json" in text     # the one-shot artifact holds ONLY the primary file
    assert "tests/test_alpha_opportunity_v5_diagnostics.py" in text


# --------------------------------------------------------------------------- #
# Durable primary isolation: the primary file exists BEFORE any diagnostic runs and is never touched again
# --------------------------------------------------------------------------- #
def cli():
    from scripts import execute_alpha_opportunity_model_v5 as CLI
    return CLI


def persisting(tmp_path, seen=None):
    """A `persist_primary` callback that writes through the CLI's own atomic writer, recording what it wrote."""
    output = tmp_path / "out"

    def persist(data):
        cli().write_primary(output, X.RESULT_NAME, data)
        if seen is not None:
            seen.append(data)
    return output, persist


def test_the_primary_file_is_physically_written_before_any_diagnostic_is_invoked(leaky, monkeypatch, tmp_path):
    replay_primary(leaky, monkeypatch)
    output, persist = persisting(tmp_path)
    at_diagnostic_time = {}

    def diagnostic(*a, **k):
        target = output / X.RESULT_NAME
        at_diagnostic_time["exists"] = target.is_file()
        at_diagnostic_time["bytes"] = target.read_bytes() if target.is_file() else None
        raise RuntimeError("stop here: only the ordering is under test")

    monkeypatch.setattr(D, "run_supplemental", diagnostic)
    out = D.execute_with_diagnostics(run_kwargs={"runtime_spec": W.runtime()}, diag=diag, diag_sha=W.DIAG_SHA,
                                     harness_hashes=HARNESS, persist_primary=persist)
    assert at_diagnostic_time["exists"] is True
    assert at_diagnostic_time["bytes"] == out["primaryBytes"] == (output / X.RESULT_NAME).read_bytes()
    assert not list(output.glob("*.partial"))                                   # the atomic write left no temp file


def test_a_normal_diagnostic_exception_leaves_the_persisted_primary_byte_identical(leaky, monkeypatch, tmp_path):
    replay_primary(leaky, monkeypatch)
    output, persist = persisting(tmp_path)
    monkeypatch.setattr(D, "run_supplemental", lambda *a, **k: (_ for _ in ()).throw(MemoryError("diagnostic OOM")))
    out = D.execute_with_diagnostics(run_kwargs={"runtime_spec": W.runtime()}, diag=diag, diag_sha=W.DIAG_SHA,
                                     harness_hashes=HARNESS, persist_primary=persist)
    persisted = (output / X.RESULT_NAME).read_bytes()
    assert out["diagnosticStatus"] == D.DIAGNOSTIC_ERROR and out["references"]["error"]["code"] == "MemoryError"
    assert persisted == out["primaryBytes"] == X.finalize(leaky["result"])
    doc = json.loads(persisted)
    assert doc["overallStatus"] in ("PASS", "FAIL", "INCONCLUSIVE", "DATA_INSUFFICIENT") and doc["substantiveResult"] is True


@pytest.mark.parametrize("failure", [SystemExit(137), KeyboardInterrupt()])
def test_a_process_level_diagnostic_failure_leaves_a_valid_primary_on_disk(leaky, monkeypatch, tmp_path, failure):
    replay_primary(leaky, monkeypatch)
    output, persist = persisting(tmp_path)

    def killed(*a, **k):
        raise failure

    monkeypatch.setattr(D, "run_supplemental", killed)
    with pytest.raises(type(failure)):                       # a process-level stop is NOT swallowed as a diagnostic error
        D.execute_with_diagnostics(run_kwargs={"runtime_spec": W.runtime()}, diag=diag, diag_sha=W.DIAG_SHA,
                                   harness_hashes=HARNESS, persist_primary=persist)
    persisted = (output / X.RESULT_NAME).read_bytes()
    doc = json.loads(persisted)
    assert persisted == X.finalize(leaky["result"]) and doc["resultDigests"]["substantiveResultSha256"] == leaky["frozen"]["sha256"]
    assert X.substantive_digest({k: v for k, v in doc.items() if k != "resultDigests"}) == leaky["frozen"]["sha256"]
    assert doc["substantiveResult"] is True and not (output / "diagnostics").exists()


def test_a_hard_kill_of_the_process_after_the_primary_write_leaves_the_primary_intact(tmp_path):
    import os
    import signal
    import subprocess
    output = tmp_path / "out"
    payload = b'{"primary":"complete"}\n'
    code = (
        "import os, signal, sys\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "from pathlib import Path\n"
        "from scripts import execute_alpha_opportunity_model_v5 as CLI\n"
        f"CLI.write_primary(Path({str(output)!r}), 'alpha-opportunity-model-v5-result.json', {payload!r})\n"
        "os.kill(os.getpid(), signal.SIGKILL)        # the 'diagnostics' die abruptly, as an OOM kill would\n")
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, cwd=ROOT)
    assert proc.returncode == -signal.SIGKILL
    assert (output / "alpha-opportunity-model-v5-result.json").read_bytes() == payload
    assert not list(output.glob("*.partial")) and not (output / "diagnostics").exists()
    assert os.path.isdir(output)


def test_diagnostic_artifacts_cannot_overwrite_or_shadow_the_primary_path(tmp_path):
    CLI = cli()
    output = tmp_path / "out"
    CLI.write_primary(output, X.RESULT_NAME, b"PRIMARY")
    with pytest.raises(CLI.Refusal, match="PRIMARY_RESULT_ALREADY_EXISTS"):
        CLI.write_primary(output, X.RESULT_NAME, b"SECOND WRITE")
    assert (output / X.RESULT_NAME).read_bytes() == b"PRIMARY"
    for name in (X.RESULT_NAME, CLI.GATES_ONLY_NAME, "../" + X.RESULT_NAME, "sub/../../x"):
        with pytest.raises(CLI.Refusal, match="MAY_NOT_TOUCH_A_PRIMARY_PATH"):
            CLI.write_diagnostics({"diagnosticArtifacts": {name: b"garbage"}, "referencesBytes": None}, output)
    assert (output / X.RESULT_NAME).read_bytes() == b"PRIMARY"
    CLI.write_diagnostics({"diagnosticArtifacts": {D.ARTIFACTS["models"]: b"{}"}, "referencesBytes": b"{}"}, output)
    assert sorted(p.name for p in (output / "diagnostics").iterdir()) == sorted([D.ARTIFACTS["models"], D.REFERENCES_NAME])
    assert (output / X.RESULT_NAME).read_bytes() == b"PRIMARY"


def test_status_claims_digest_and_payload_are_unchanged_by_diagnostics_even_when_they_fail(leaky, monkeypatch, tmp_path):
    replay_primary(leaky, monkeypatch)
    written = {}
    for label, behaviour in (("off", None), ("ok", "real"), ("error", "raise")):
        output, persist = persisting(tmp_path / label)
        if behaviour == "raise":
            monkeypatch.setattr(D, "run_supplemental", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
        elif behaviour == "real":
            monkeypatch.setattr(D, "run_supplemental", supplemental_real)
        out = D.execute_with_diagnostics(run_kwargs={"runtime_spec": W.runtime(CUTOFF)},
                                         diag=None if behaviour is None else diag, diag_sha=W.DIAG_SHA,
                                         harness_hashes=HARNESS, persist_primary=persist)
        written[label] = ((output / X.RESULT_NAME).read_bytes(), out["frozen"]["sha256"])
    assert written["off"] == written["ok"] == written["error"]
    doc = json.loads(written["off"][0])
    assert doc["resultDigests"]["substantiveResultSha256"] == written["off"][1] == leaky["frozen"]["sha256"]


REAL_SUPPLEMENTAL = D.run_supplemental          # captured at import, before any test patches the module attribute


def supplemental_real(ctx, **kwargs):
    return REAL_SUPPLEMENTAL(ctx, **kwargs)


def test_a_diagnostic_failure_creates_no_retry_authority(leaky, monkeypatch, tmp_path):
    replay_primary(leaky, monkeypatch)
    output, persist = persisting(tmp_path)
    monkeypatch.setattr(D, "run_supplemental", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    out = D.execute_with_diagnostics(run_kwargs={"runtime_spec": W.runtime()}, diag=diag, diag_sha=W.DIAG_SHA,
                                     harness_hashes=HARNESS, persist_primary=persist)
    refs = out["references"]
    assert refs["status"] == D.DIAGNOSTIC_ERROR and refs["authorizesRetry"] is False and refs["changesPrimary"] is False
    doc = json.loads((output / X.RESULT_NAME).read_bytes())
    assert doc["substantiveResult"] is True and doc["closesPreregistration"] is True and doc["overallStatus"] != "INFRASTRUCTURE_ERROR"
    text = (output / X.RESULT_NAME).read_text()
    assert "DIAGNOSTIC_ERROR" not in text and "retry" not in text.lower()


def test_a_failure_during_primary_computation_still_yields_no_false_substantive_result(monkeypatch, tmp_path):
    spy = []
    monkeypatch.setattr(D, "run_supplemental", lambda *a, **k: spy.append(1))
    world = W.make_world(seed=5, n=12)

    def add_us(frame):
        us = frame.iloc[:5].copy()
        us["region"] = "US"
        return pd.concat([frame, us], ignore_index=True)

    output, persist = persisting(tmp_path)
    out = D.execute_with_diagnostics(run_kwargs=W.run_kwargs(world, frame_mutator=add_us), diag=diag, diag_sha=W.DIAG_SHA,
                                     harness_hashes=HARNESS, persist_primary=persist)
    doc = json.loads((output / X.RESULT_NAME).read_bytes())
    assert doc["overallStatus"] == "INFRASTRUCTURE_ERROR" and doc["substantiveResult"] is False
    assert doc["closesPreregistration"] is False and all(c["status"] == "INFRASTRUCTURE_ERROR" for c in doc["claims"].values())
    assert spy == [] and out["diagnosticStatus"] == D.NOT_RUN and out["diagnosticArtifacts"] == {}
    assert out["references"]["authorizesRetry"] is False


def test_the_one_shot_authorization_and_main_only_guards_are_unchanged(tmp_path):
    CLI = cli()
    none_committed = tmp_path / "none.json"
    with pytest.raises(CLI.Refusal, match="AUTHORIZATION_MISSING"):
        CLI.verify_authorization(tmp_path / "absent.json", spec_sha256=W.SPEC_SHA, harness_files={},
                                 diagnostic_spec_sha256=W.DIAG_SHA, committed_result=none_committed)
    committed = tmp_path / "alpha-opportunity-model-v5-result.json"
    committed.write_text("{}")
    with pytest.raises(CLI.Refusal, match="A_COMMITTED_V5_RESULT_ALREADY_EXISTS"):
        CLI.verify_authorization(tmp_path / "absent.json", spec_sha256=W.SPEC_SHA, harness_files={},
                                 diagnostic_spec_sha256=W.DIAG_SHA, committed_result=committed)
    with pytest.raises(CLI.Refusal, match="ONLY_FROM_MAIN"):
        CLI.require_actions_main({"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/other"})
    text = (ROOT / ".github/workflows/alpha-opportunity-model-v5-execution.yml").read_text()
    assert "github.ref != 'refs/heads/main'" in text and "expired==false" in text and "one-shot" in text
    assert "authorization.json" in text


def test_workflow_classifies_and_uploads_the_primary_even_if_the_diagnostic_process_died():
    import re
    text = (ROOT / ".github/workflows/alpha-opportunity-model-v5-execution.yml").read_text()
    for anchor in ("id: classify", "name: alpha-opportunity-model-v5-result", "name: alpha-opportunity-model-v5-diagnostics"):
        block = text[text.index(anchor) - 200:text.index(anchor) + 200]
        assert "always() && inputs.mode == 'execute'" in block, anchor
    assert re.search(r"alpha-opportunity-model-v5-result\n\s+path: \$\{\{ runner\.temp \}\}/v5-result/alpha-opportunity-model-v5-result\.json", text)
    assert "alpha-opportunity-model-v5-diagnostic-references.json" in text
    execute = text[text.index("id: execute"):text.index("id: classify")]
    assert "exit 0" in execute and "PIPESTATUS" in execute            # a dying diagnostic process cannot fail the step early
    assert '"NO_ARTIFACT"' in text and "INFRASTRUCTURE_ERROR" in text  # a missing/invalid primary still fails the job
