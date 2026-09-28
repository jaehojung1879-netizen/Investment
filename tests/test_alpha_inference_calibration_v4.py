import ast
import builtins
import copy
import hashlib
import io
import json
import math
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np
import pytest
from scipy.stats import binom

from pipeline import alpha_inference_calibration_v4 as v4
from pipeline import alpha_inference_mc_decision as mc
from pipeline.alpha_inference_calibration_v3 import _self_normalized_interval
from pipeline.alpha_inference_exact_coverage import (
    calendar_map,
    gaussian_coverage,
    self_normalized_form,
)

SPEC_PATH = Path("research_specs/alpha-inference-calibration-v4.json")
V3_SPEC_PATH = Path("research_specs/alpha-inference-calibration-v3.json")
WORKFLOW = Path(".github/workflows/alpha-inference-calibration-v4.yml")
C = 66.57
TOL = 1e-12


def _spec():
    return json.loads(SPEC_PATH.read_text())


def _tiny_spec(weeks=12, horizon=21, dgp_index=5, replicates=3):
    spec = _spec()
    spec["dgps"] = [spec["dgps"][dgp_index]]
    spec["horizons"] = {str(horizon): {"forwardSessions": horizon, "calendarWeeks": [weeks]}}
    spec["minimumConfirmatoryDepth"] = {str(horizon): {"calendarWeeks": weeks}}
    spec["simulationReplicates"] = replicates
    return spec


def _draw(spec=None, dgp_index=0, horizon=21, weeks=10, replicate=0):
    spec = spec or _spec()
    return v4.simulate_replicate(
        spec, spec["dgps"][dgp_index], horizon=horizon, weeks=weeks, replicate=replicate, dgp_index=dgp_index
    )


# ---------------------------------------------------------------- protocol
def test_v3_remains_frozen_and_is_referenced_as_fail():
    assert hashlib.sha256(V3_SPEC_PATH.read_bytes()).hexdigest() == (
        "e8340ac3541e8981983996b8a66b54030757c2cd0419aab2140f8e3fe41d1d59"
    )
    ref = _spec()["v3FailureReference"]
    assert ref["primaryStatus"] == "FAIL"
    assert ref["specSha256"] == hashlib.sha256(V3_SPEC_PATH.read_bytes()).hexdigest()
    assert ref["workflowRun"] == 36483954346


def test_v4_keeps_v3_tolerances_depths_confidence_and_inherited_dgps():
    v3, spec = json.loads(V3_SPEC_PATH.read_text()), _spec()
    for key in ("materialCoverageFloor", "directionalFalsePositiveCeiling",
                "undefinedFrequencyCeiling", "maximumMonteCarlo95HalfWidth"):
        assert spec["acceptance"][key] == v3["acceptance"][key]
    for key in ("familywiseAlpha", "primaryExpectedReturnClaims", "cellTwoSidedAlpha", "nominalCoverage"):
        assert spec["confidence"][key] == v3["confidence"][key]
    assert spec["horizons"] == v3["horizons"]
    assert spec["intervalConstruction"]["U1CriticalValue"] == v3["intervalConstruction"]["U1CriticalValue"]
    for key in ("namesPerDate", "signalStepSessions", "selectionFraction", "syntheticForecastScale"):
        assert spec[key] == v3[key]
    inherited = spec["dgps"][: len(v3["dgps"])]
    for old, new in zip(v3["dgps"], inherited):
        assert {k: new[k] for k in old} == old
        assert new["phiPredictor"] == 0.0 and new["innovation"] == "GAUSSIAN"
    assert spec["seed"] != v3["seed"]
    assert spec["simulationReplicates"] >= 1825  # the frozen 1pp precision criterion


def test_protocol_validates_and_refuses_tampering():
    spec = _spec()
    v4.validate_spec(spec)
    for mutate in (
        lambda s: s.update(contract="ALPHA_INFERENCE_CALIBRATION_V3"),
        lambda s: s["intervalConstruction"].update(U1CriticalValue=45.4),
        lambda s: s["intervalConstruction"].update(blockLength=52),
        lambda s: s["statistics"].update(confirmatory=["dateMean"]),
        lambda s: s["statistics"].update(descriptive=[]),
        lambda s: s["minimumConfirmatoryDepth"].pop("126"),
        lambda s: s["dgps"][0].update(innovation="CAUCHY"),
    ):
        broken = copy.deepcopy(spec)
        mutate(broken)
        with pytest.raises(ValueError, match="INVALID_V4_PROTOCOL"):
            v4.validate_spec(broken)


# ---------------------------------------------------------------- synthetic null
def test_simulation_is_deterministic():
    a, b = _draw(replicate=4), _draw(replicate=4)
    for key in a:
        assert np.array_equal(a[key], b[key])
    c = _draw(replicate=5)
    assert not np.array_equal(a["daily"], c["daily"])


def test_rng_streams_are_separated_between_returns_and_predictors():
    spec = _spec()
    base = _draw(spec, dgp_index=2)
    changed = copy.deepcopy(spec)
    changed["dgps"][2]["phiPredictor"] = 0.9
    other = _draw(changed, dgp_index=2)
    assert np.array_equal(base["daily"], other["daily"])  # predictor settings never touch returns
    assert not np.array_equal(base["scoreA"], other["scoreA"])

    louder = copy.deepcopy(spec)
    louder["dgps"][2]["sigmaShared"] = 3.0
    loud = _draw(louder, dgp_index=2)
    for key in ("scoreA", "scoreB", "selectionScore"):
        assert np.array_equal(base[key], loud[key])  # return settings never touch predictors


def test_predictors_are_persistent_only_when_registered():
    spec = _spec()
    iid = _draw(spec, dgp_index=0, weeks=400)["scoreA"]
    persistent = _draw(spec, dgp_index=4, weeks=400)["scoreA"]

    def lag1(x):
        return float(np.mean([np.corrcoef(x[:-1, i], x[1:, i])[0, 1] for i in range(x.shape[1])]))

    assert abs(lag1(iid)) < 0.05
    assert 0.9 < lag1(persistent) < 0.99


def test_student_t_innovations_have_unit_variance_and_heavy_tails():
    rng = np.random.default_rng(3)
    draws = v4._innovations(rng, (400_000, 1), {"innovation": "STUDENT_T", "studentTDegreesOfFreedom": 4})
    assert abs(draws.var() - 1.0) < 0.05
    gauss = v4._innovations(rng, (400_000, 1), {"innovation": "GAUSSIAN"})
    assert np.mean(draws**4) > 2 * np.mean(gauss**4)


def test_overlapping_forward_sums_match_brute_force():
    rng = np.random.default_rng(1)
    weeks, horizon, step = 7, 13, 5
    daily = rng.normal(size=((weeks - 1) * step + horizon, 4))
    forward = v4.forward_sums(daily, weeks, horizon, step)
    for t in range(weeks):
        assert np.allclose(forward[t], daily[step * t: step * t + horizon].sum(axis=0))
    with pytest.raises(ValueError):
        v4.forward_sums(daily[:-1], weeks, horizon, step)


def test_selection_is_frozen_top_fraction_and_rank_weights_are_dollar_neutral():
    spec = _spec()
    draw = _draw(spec, weeks=9)
    designs = v4.statistic_designs(spec, draw)
    selected = designs["selectedMean"]["weights"]
    assert np.allclose(selected.sum(axis=1), 1.0)
    assert ((selected > 0).sum(axis=1) == 12).all()
    for t in range(selected.shape[0]):
        top = np.argsort(draw["selectionScore"][t])[-12:]
        assert set(np.flatnonzero(selected[t])) == set(top)
    assert np.allclose(designs["selectedMinusUniverse"]["weights"].sum(axis=1), 0.0)
    rank = designs["rankWeightedSpread"]["weights"]
    assert np.allclose(rank.sum(axis=1), 0.0)
    assert np.allclose(np.where(rank > 0, rank, 0).sum(axis=1), 1.0)
    order = np.argsort(draw["scoreA"][0])
    assert (np.diff(rank[0][order]) > 0).all()


def test_linear_designs_reproduce_direct_statistic_definitions():
    spec = _spec()
    weeks, horizon = 11, 21
    draw = _draw(spec, weeks=weeks, horizon=horizon)
    forward = v4.forward_sums(draw["daily"], weeks, horizon, 5)
    designs = v4.statistic_designs(spec, draw)
    pa, pb = 0.25 * draw["scoreA"], 0.25 * draw["scoreB"]
    direct_mse = np.mean((pb - forward) ** 2 - (pa - forward) ** 2, axis=1)
    got = v4.signal_date_series(forward, designs["pairedMseImprovement"]["weights"],
                                designs["pairedMseImprovement"]["signalTerm"])
    assert np.allclose(got, direct_mse)
    assert np.allclose(v4.signal_date_series(forward, designs["dateMean"]["weights"]), forward.mean(axis=1))


# ---------------------------------------------------------------- attribution
def test_calendar_attribution_is_an_exact_identity_for_every_statistic():
    spec = _spec()
    for horizon, weeks in ((21, 9), (126, 30)):
        draw = _draw(spec, dgp_index=5, weeks=weeks, horizon=horizon)
        forward = v4.forward_sums(draw["daily"], weeks, horizon, 5)
        for design in v4.statistic_designs(spec, draw).values():
            d, x = v4.calendar_time_series(draw["daily"], design["weights"], horizon, 5, design["signalTerm"])
            by_date = v4.signal_date_series(forward, design["weights"], design["signalTerm"])
            assert math.isclose(d.sum(), by_date.sum(), rel_tol=1e-10, abs_tol=1e-9)
            assert math.isclose(x.sum(), weeks)
            assert len(d) == -(-((weeks - 1) * 5 + horizon) // 5)


def test_calendar_attribution_matches_brute_force_cohort_loop():
    rng = np.random.default_rng(2)
    weeks, horizon, step, names = 6, 12, 5, 3
    sessions = (weeks - 1) * step + horizon
    daily = rng.normal(size=(sessions, names))
    weights = rng.normal(size=(weeks, names))
    term = rng.normal(size=weeks)
    d, x = v4.calendar_time_series(daily, weights, horizon, step, term)
    brute = np.zeros(-(-sessions // step))
    exposure = np.zeros_like(brute)
    for t in range(weeks):
        brute[t] += term[t]
        for s in range(step * t, step * t + horizon):
            brute[s // step] += weights[t] @ daily[s]
            exposure[s // step] += 1.0 / horizon
    assert np.allclose(d, brute)
    assert np.allclose(x, exposure)
    _, analytic_x = calendar_map(weeks, horizon, step)
    assert np.allclose(x, analytic_x)


def test_one_shock_enters_one_calendar_week_but_every_overlapping_signal_date():
    weeks, horizon, step, names = 40, 126, 5, 2
    daily = np.zeros(((weeks - 1) * step + horizon, names))
    daily[150, :] = 1.0  # interior session: 26 cohorts contain it
    weights = np.full((weeks, names), 1.0 / names)
    d, _ = v4.calendar_time_series(daily, weights, horizon, step)
    by_date = v4.signal_date_series(v4.forward_sums(daily, weeks, horizon, step), weights)
    assert np.count_nonzero(d) == 1
    assert np.count_nonzero(by_date) == math.ceil(horizon / step)


def test_shared_cross_sectional_shock_passes_through_date_mean_attribution():
    weeks, horizon, step, names = 8, 21, 5, 5
    shared = np.random.default_rng(4).normal(size=(weeks - 1) * step + horizon)
    daily = np.repeat(shared[:, None], names, axis=1)
    weights = np.full((weeks, names), 1.0 / names)
    d, x = v4.calendar_time_series(daily, weights, horizon, step)
    mapping, _ = calendar_map(weeks, horizon, step)
    assert np.allclose(d, mapping @ shared)


def test_undefined_dates_contribute_nothing_and_estimate_is_mean_over_defined_dates():
    rng = np.random.default_rng(5)
    weeks, horizon, step = 10, 21, 5
    daily = rng.normal(size=((weeks - 1) * step + horizon, 4))
    weights = rng.normal(size=(weeks, 4))
    defined = np.ones(weeks, dtype=bool)
    defined[[2, 7]] = False
    d, x = v4.calendar_time_series(daily, weights, horizon, step, defined=defined)
    by_date = v4.signal_date_series(v4.forward_sums(daily, weeks, horizon, step), weights)
    interval = v4.calendar_time_sn_interval(d, x, C, TOL)
    assert math.isclose(x.sum(), 8.0)
    assert math.isclose(interval["estimate"], by_date[defined].mean())
    d0, x0 = v4.calendar_time_series(daily, weights, horizon, step, defined=np.zeros(weeks, dtype=bool))
    assert v4.calendar_time_sn_interval(d0, x0, C, TOL) is None


# ---------------------------------------------------------------- interval math
def test_unit_exposure_reduces_exactly_to_v3_interval():
    series = np.random.default_rng(6).normal(size=37)
    a = v4.calendar_time_sn_interval(series, np.ones(37), C, TOL)
    b = _self_normalized_interval(series, C)
    for key in ("estimate", "lower", "upper", "width", "selfNormalizer"):
        scale = 37**2 if key == "selfNormalizer" else 1.0
        assert math.isclose(a[key], b[key] * scale, rel_tol=1e-12, abs_tol=1e-12)


def test_interval_is_centred_on_estimate_and_equivariant():
    rng = np.random.default_rng(7)
    x = np.concatenate([np.linspace(0.2, 1.0, 5), np.ones(20), np.linspace(1.0, 0.2, 5)])
    d = rng.normal(size=len(x))
    base = v4.calendar_time_sn_interval(d, x, C, TOL)
    assert math.isclose(base["estimate"], d.sum() / x.sum())
    assert math.isclose(base["upper"] - base["estimate"], base["estimate"] - base["lower"])
    shifted = v4.calendar_time_sn_interval(2.5 * d + 3.0 * x, x, C, TOL)
    assert math.isclose(shifted["estimate"], 2.5 * base["estimate"] + 3.0)
    assert math.isclose(shifted["width"], 2.5 * base["width"])


def test_zero_and_near_zero_normalizer_are_undefined_not_false_certainty():
    x = np.concatenate([np.linspace(0.2, 1.0, 5), np.ones(20)])
    assert v4.calendar_time_sn_interval(4.0 * x, x, C, TOL) is None
    noise = np.random.default_rng(8).normal(scale=1e-15, size=len(x))
    assert v4.calendar_time_sn_interval(4.0 * x + noise, x, C, TOL) is None
    assert v4.calendar_time_sn_interval(np.zeros(25), x, C, TOL) is None


def test_short_or_invalid_series_are_undefined():
    assert v4.calendar_time_sn_interval(np.array([1.0]), np.array([1.0]), C, TOL) is None
    assert v4.calendar_time_sn_interval(np.array([1.0, np.nan]), np.ones(2), C, TOL) is None
    assert v4.calendar_time_sn_interval(np.array([1.0, 2.0]), np.array([1.0, -1.0]), C, TOL) is None
    assert v4.calendar_time_sn_interval(np.array([1.0, 2.0]), np.zeros(2), C, TOL) is None
    with pytest.raises(ValueError):
        v4.calendar_time_sn_interval(np.array([1.0, 2.0]), np.ones(2), -1.0, TOL)


def test_exact_coverage_instrument_matches_brute_force_and_nominal_iid_level():
    n, rho = 40, 0.6
    lags = np.arange(n)
    sigma = rho ** np.abs(lags[:, None] - lags[None, :])
    exact = gaussian_coverage(sigma, self_normalized_form(np.ones(n), C))
    rng = np.random.default_rng(9)
    y = rng.normal(size=(100_000, n)) @ np.linalg.cholesky(sigma).T
    covered = [
        (lambda r: r["lower"] <= 0.0 <= r["upper"])(_self_normalized_interval(row, C)) for row in y[:20_000]
    ]
    assert abs(exact - np.mean(covered)) < 0.006
    iid = gaussian_coverage(np.eye(200), self_normalized_form(np.ones(200), C))
    assert abs(iid - 0.975) < 0.003


# ---------------------------------------------------------------- depth and status
@pytest.mark.parametrize("horizon,floor", [(21, 78), (126, 312)])
def test_minimum_confirmatory_depth_boundaries(horizon, floor):
    spec = _spec()
    assert v4.confirmatory_depth_status(spec, horizon, floor) == "ELIGIBLE"
    assert v4.confirmatory_depth_status(spec, horizon, floor - 1) == (
        f"DATA_INSUFFICIENT_FOR_CONFIRMATORY_H{horizon}_INFERENCE"
    )
    assert v4.confirmatory_depth_status(spec, 63, 10_000).startswith("DATA_INSUFFICIENT")


def test_run_reports_data_insufficient_for_uncalibrated_depth():
    spec = _tiny_spec(weeks=12)
    spec["minimumConfirmatoryDepth"]["21"]["calendarWeeks"] = 13
    result = v4.run_calibration(spec, formal=False)
    assert result["primaryStatus"] == "DATA_INSUFFICIENT"
    assert result["cells"][0]["statistics"] is None


def test_tiny_run_is_complete_and_rank_ic_never_gates():
    result = v4.run_calibration(_tiny_spec(replicates=2), formal=False)
    cell = result["cells"][0]
    assert set(cell["statistics"]) == set(v4.CONFIRMATORY)
    assert "rankIC" not in cell["statistics"] and "rankIC" not in cell["failures"]
    assert "rankIC" not in cell["inconclusive"]
    assert "rankIC" in cell["descriptive"]
    assert result["primaryStatus"] in v4.STATUSES
    for decision in cell["statistics"].values():
        assert set(decision["metrics"]) == {"coverage", "positiveFalsePositive", "undefinedFrequency"}


def test_calibration_opens_no_file(monkeypatch):
    spec = _tiny_spec(replicates=2)

    def refuse(*args, **kwargs):
        raise AssertionError(f"file access attempted: {args}")

    monkeypatch.setattr(builtins, "open", refuse)
    monkeypatch.setattr(Path, "open", refuse)
    monkeypatch.setattr(Path, "read_text", refuse)
    monkeypatch.setattr(Path, "read_bytes", refuse)
    v4.run_calibration(spec, formal=False)


def test_modules_import_no_data_or_production_code():
    allowed = {
        "__future__", "math", "typing", "numpy", "hashlib", "json", "scipy.signal", "scipy.integrate",
        "scipy.stats", "pipeline", "pipeline.alpha_inference_mc_decision",
        "pipeline.alpha_inference_calibration_v1", "pipeline.alpha_inference_calibration_v3",
    }
    for path in ("pipeline/alpha_inference_calibration_v4.py", "pipeline/alpha_inference_exact_coverage.py",
                 "pipeline/alpha_inference_mc_decision.py"):
        tree = ast.parse(Path(path).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module]
            else:
                continue
            assert set(names) <= allowed, (path, names)
        assert "open(" not in Path(path).read_text()


# ---------------------------------------------------------------- runner and workflow
def _run(argv):
    from scripts.run_alpha_inference_calibration_v4 import main

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(argv)
    return code, buffer.getvalue()


def test_runner_is_deterministic_and_labels_development_runs(tmp_path):
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps(_tiny_spec(replicates=2)))
    out1, out2, out3 = tmp_path / "a.json", tmp_path / "b.json", tmp_path / "c.json"
    for out, seed in ((out1, 11), (out2, 11), (out3, 12)):
        code, printed = _run(["--spec", str(spec_file), "--output", str(out),
                              "--development-smoke", "2", "--development-seed", str(seed)])
        assert code == 0
        assert hashlib.sha256(spec_file.read_bytes()).hexdigest() in printed
    assert out1.read_bytes() == out2.read_bytes()
    a, c = json.loads(out1.read_text()), json.loads(out3.read_text())
    assert a["runClass"] == "DEVELOPMENT_ONLY" and a["verdictAuthority"] == "NONE_DEVELOPMENT_ONLY"
    assert a["cells"] != c["cells"]
    assert {k: v for k, v in a.items() if k not in ("cells", "primaryFailures", "primaryStatus", "seedUsed")} == {
        k: v for k, v in c.items() if k not in ("cells", "primaryFailures", "primaryStatus", "seedUsed")
    }


def test_runner_refuses_real_data_paths_and_formal_seed_reuse(tmp_path):
    for bad in ("ledger/x.json", "data/site-data.json", "docs/results/x.json", "signal-history/x.json"):
        with pytest.raises(SystemExit, match="REFUSED"):
            _run(["--output", bad])
        with pytest.raises(SystemExit, match="REFUSED"):
            _run(["--spec", bad, "--output", str(tmp_path / "o.json")])
    with pytest.raises(SystemExit, match="formal seed"):
        _run(["--output", str(tmp_path / "o.json"), "--development-smoke", "2",
              "--development-seed", str(_spec()["seed"])])


def test_runner_writes_infrastructure_error_artifact(tmp_path):
    spec = _tiny_spec()
    spec["contract"] = "NOT_V4"
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps(spec))
    out = tmp_path / "o.json"
    code, _ = _run(["--spec", str(spec_file), "--output", str(out)])
    assert code == 1
    assert json.loads(out.read_text())["primaryStatus"] == "INFRASTRUCTURE_ERROR"


def test_workflow_is_manual_secret_free_main_only_and_always_uploads():
    text = "\n".join(line for line in WORKFLOW.read_text().splitlines() if not line.lstrip().startswith("#"))
    assert "workflow_dispatch" in text
    for forbidden in ("schedule:", "push:", "pull_request", "secrets.", "signal-history", "--development-smoke"):
        assert forbidden not in text
    assert "refs/heads/main" in text
    assert "if: always()" in text
    assert "contents: read" in text


# ---------------------------------------------------------------- Monte Carlo decision rule
PASS_A, FAIL_A = 0.025, 0.05 / 360


def _floor(k, n, **kw):
    return mc.classify_metric(k, n, kind=mc.FLOOR, threshold=0.95, pass_alpha=PASS_A, fail_alpha=FAIL_A, **kw)


def _ceiling(k, n, **kw):
    return mc.classify_metric(k, n, kind=mc.CEILING, threshold=0.05, pass_alpha=PASS_A, fail_alpha=FAIL_A, **kw)


def test_frozen_monte_carlo_decision_levels_and_count_are_consistent_with_the_registry():
    spec = _spec()
    cfg = spec["monteCarloDecision"]
    assert cfg["intervalMethod"] == "CLOPPER_PEARSON_EXACT_ONE_SIDED"
    assert cfg["passSideOneSidedAlpha"] == 0.025 and cfg["failSideFamilywiseAlpha"] == 0.05
    assert cfg["failSideDecisionCount"] == v4.decision_count(spec) == 24 * 5 * 3
    assert cfg["levelsFrozenBeforeFormalRun"] is True
    assert spec["simulationReplicates"] == 2000
    # the Monte Carlo levels are a separate contract from the statistical interval's 97.5% claim level
    assert spec["confidence"]["nominalCoverage"] == 0.975 and "purpose" in cfg


def test_clopper_pearson_bounds_are_exact_deterministic_and_monotone():
    n = 500
    assert mc.clopper_pearson_lower(0, n, 0.025) == 0.0
    assert mc.clopper_pearson_upper(n, n, 0.025) == 1.0
    # closed forms at the edges: (alpha)^(1/n) and 1 - alpha^(1/n)
    assert math.isclose(mc.clopper_pearson_lower(n, n, 0.025), 0.025 ** (1 / n), rel_tol=1e-12)
    assert math.isclose(mc.clopper_pearson_upper(0, n, 0.025), 1 - 0.025 ** (1 / n), rel_tol=1e-12)
    lowers = [mc.clopper_pearson_lower(k, n, 0.025) for k in range(n + 1)]
    uppers = [mc.clopper_pearson_upper(k, n, 0.025) for k in range(n + 1)]
    assert all(np.isfinite(lowers)) and all(np.isfinite(uppers))
    assert all(a <= b for a, b in zip(lowers, lowers[1:])) and all(a <= b for a, b in zip(uppers, uppers[1:]))
    assert all(lo <= k / n <= up for k, (lo, up) in enumerate(zip(lowers, uppers)))
    assert mc.clopper_pearson_lower(437, n, 0.025) == mc.clopper_pearson_lower(437, n, 0.025)


def test_clopper_pearson_defining_property_holds_exactly():
    n, alpha = 300, 0.025
    for k in (1, 150, 290, 299):
        lo = mc.clopper_pearson_lower(k, n, alpha)
        up = mc.clopper_pearson_upper(k, n, alpha)
        assert math.isclose(binom.sf(k - 1, n, lo), alpha, rel_tol=1e-9)   # P(X >= k | lo) = alpha
        assert math.isclose(binom.cdf(k, n, up), alpha, rel_tol=1e-9)       # P(X <= k | up) = alpha


def test_interval_helpers_reject_bad_inputs():
    for bad in ((-1, 10, 0.025), (11, 10, 0.025), (5, 10, 0.0), (5, 10, 0.5)):
        with pytest.raises(ValueError):
            mc.clopper_pearson_lower(*bad)
    with pytest.raises(TypeError):
        mc.clopper_pearson_lower(2.0, 10, 0.025)
    with pytest.raises(ValueError):
        mc.classify_metric(5, 10, kind="MIDDLE", threshold=0.5, pass_alpha=0.025, fail_alpha=0.01)


def test_floor_metric_three_states_and_exact_threshold_adjacent_counts():
    n = 2000
    assert _floor(1950, n)["state"] == mc.PASS            # 0.975
    assert _floor(1800, n)["state"] == mc.FAIL            # 0.90
    assert _floor(1900, n)["state"] == mc.INCONCLUSIVE    # 0.95 exactly: point estimate on the floor
    # the smallest count that passes, and the count one below it
    first = next(k for k in range(n + 1) if _floor(k, n)["state"] == mc.PASS)
    assert _floor(first, n)["state"] == mc.PASS and _floor(first - 1, n)["state"] == mc.INCONCLUSIVE
    assert first / n > 0.95  # a point estimate above the floor is not enough to PASS
    assert _floor(first, n)["lowerBoundPassSide"] >= 0.95 > _floor(first - 1, n)["lowerBoundPassSide"]
    # and the largest count that fails
    last = max(k for k in range(n + 1) if _floor(k, n)["state"] == mc.FAIL)
    assert _floor(last + 1, n)["state"] == mc.INCONCLUSIVE and last / n < 0.95
    assert _floor(0, n)["state"] == mc.FAIL and _floor(n, n)["state"] == mc.PASS


def test_ceiling_metric_three_states():
    n = 2000
    assert _ceiling(20, n)["state"] == mc.PASS            # 1%
    assert _ceiling(200, n)["state"] == mc.FAIL           # 10%
    assert _ceiling(100, n)["state"] == mc.INCONCLUSIVE   # 5% exactly
    first_fail = min(k for k in range(n + 1) if _ceiling(k, n)["state"] == mc.FAIL)
    assert first_fail / n > 0.05 and _ceiling(first_fail - 1, n)["state"] == mc.INCONCLUSIVE
    assert _ceiling(0, n)["state"] == mc.PASS and _ceiling(n, n)["state"] == mc.FAIL


def test_pass_and_fail_can_never_both_hold_and_states_are_monotone_in_successes():
    n = 300
    order = {mc.FAIL: 0, mc.INCONCLUSIVE: 1, mc.PASS: 2}
    floor_ranks = [order[_floor(k, n)["state"]] for k in range(n + 1)]
    ceiling_ranks = [order[_ceiling(k, n)["state"]] for k in range(n + 1)]
    assert floor_ranks == sorted(floor_ranks)                      # more successes never hurts a floor metric
    assert ceiling_ranks == sorted(ceiling_ranks, reverse=True)    # more events never helps a ceiling metric


def test_zero_measurable_replicates_is_inconclusive_not_a_pass_or_a_nan():
    record = _floor(0, 0)
    assert record["state"] == mc.INCONCLUSIVE and record["reason"] == "NO_MEASURABLE_REPLICATES"
    assert record["estimate"] is None
    assert _ceiling(2000, 2000)["state"] == mc.FAIL  # every replicate undefined -> the undefined metric FAILs


def test_precision_guard_blocks_pass_but_never_masks_fail():
    kw = dict(kind=mc.FLOOR, threshold=0.95, pass_alpha=PASS_A, fail_alpha=FAIL_A)
    assert mc.classify_metric(1990, 2000, max_half_width=0.04, **kw)["state"] == mc.PASS
    guarded = mc.classify_metric(1990, 2000, max_half_width=0.001, **kw)
    assert guarded["state"] == mc.INCONCLUSIVE and guarded["reason"] == "MONTE_CARLO_PRECISION_INSUFFICIENT"
    failing = mc.classify_metric(1000, 2000, max_half_width=0.001, **kw)
    assert failing["state"] == mc.FAIL


def test_fail_side_alpha_is_a_bonferroni_share_and_validated():
    assert math.isclose(mc.fail_side_alpha(0.05, 360), 0.05 / 360)
    for bad in ((0.05, 0), (0.7, 10), (0.0, 10)):
        with pytest.raises(ValueError):
            mc.fail_side_alpha(*bad)


def test_operating_characteristic_matches_documented_development_figures():
    diag = json.loads(Path("docs/results/alpha-inference-calibration-v4-development-diagnostics.json").read_text())
    oc = diag["threeStateRuleOperatingCharacteristic"]
    assert oc["replicates"] == 2000
    states = [_floor(k, 2000)["state"] for k in range(2001)]
    pmf = binom.pmf(np.arange(2001), 2000, 0.96)
    expected_pass = float(sum(p for p, st in zip(pmf, states) if st == mc.PASS))
    assert math.isclose(oc["coverageByTrueValue"]["0.960"]["PASS"], expected_pass, rel_tol=1e-9)
    # the previous point-estimate rule's operating characteristic is retained, not deleted
    assert set(diag["acceptanceRuleOperatingCharacteristic"]["byReplicates"]) == {"300", "2000"}


# ---------------------------------------------------------------- verdict precedence
def _top(states, insufficient=0, infra=False):
    return mc.top_level_status(cell_states=states, insufficient_depth_cells=insufficient, infrastructure_error=infra)


def test_top_level_precedence():
    P, F, I = mc.PASS, mc.FAIL, mc.INCONCLUSIVE
    assert _top([P, P, P]) == mc.PASS
    assert _top([P, F, P, P]) == mc.FAIL                       # one FAIL among PASSes
    assert _top([P, I, P]) == mc.INCONCLUSIVE                  # one INCONCLUSIVE, no FAIL
    assert _top([I, F]) == mc.FAIL                             # FAIL outranks INCONCLUSIVE
    assert _top([P, I], insufficient=2) == mc.INCONCLUSIVE     # documented: INCONCLUSIVE before DATA_INSUFFICIENT
    assert _top([P, P], insufficient=1) == mc.DATA_INSUFFICIENT
    assert _top([P, F], insufficient=1) == mc.FAIL
    assert _top([], insufficient=3) == mc.DATA_INSUFFICIENT
    assert _top([P, F, I], insufficient=1, infra=True) == mc.INFRASTRUCTURE_ERROR
    with pytest.raises(ValueError):
        _top([])
    with pytest.raises(ValueError):
        _top(["MAYBE"])


def test_combine_states_is_worst_of():
    assert mc.combine_states([mc.PASS, mc.PASS]) == mc.PASS
    assert mc.combine_states([mc.PASS, mc.INCONCLUSIVE]) == mc.INCONCLUSIVE
    assert mc.combine_states([mc.INCONCLUSIVE, mc.FAIL, mc.PASS]) == mc.FAIL
    with pytest.raises(ValueError):
        mc.combine_states([])


def _intervals(defined_covering, defined_missing, positive, undefined):
    ok = {"lower": -1.0, "upper": 1.0, "width": 2.0, "estimate": 0.0}
    miss = {"lower": -1.5, "upper": -0.5, "width": 1.0, "estimate": -1.0}  # misses below zero: not a positive FP
    pos = {"lower": 0.1, "upper": 1.0, "width": 0.9, "estimate": 0.5}
    return [ok] * defined_covering + [miss] * defined_missing + [pos] * positive + [None] * undefined


def test_decide_statistic_counts_and_states_from_integer_records():
    spec = _spec()
    clean = v4.decide_statistic(_intervals(1990, 0, 10, 0), 2000, spec)
    assert clean["state"] == mc.PASS and clean["failureCodes"] == []
    m = clean["metrics"]
    assert (m["coverage"]["successes"], m["coverage"]["n"]) == (1990, 2000)
    assert (m["positiveFalsePositive"]["successes"], m["positiveFalsePositive"]["n"]) == (10, 2000)
    assert m["undefinedFrequency"]["successes"] == 0

    under = v4.decide_statistic(_intervals(1700, 300, 0, 0), 2000, spec)
    assert under["state"] == mc.FAIL and under["failureCodes"] == ["MATERIAL_UNDERCOVERAGE"]

    edge = v4.decide_statistic(_intervals(1900, 100, 0, 0), 2000, spec)
    assert edge["state"] == mc.INCONCLUSIVE and edge["failureCodes"] == []
    assert edge["inconclusiveCodes"] == ["MATERIAL_UNDERCOVERAGE:MONTE_CARLO_INTERVAL_OVERLAPS_THRESHOLD"]

    fp = v4.decide_statistic(_intervals(1500, 0, 500, 0), 2000, spec)
    assert "DIRECTIONAL_FALSE_POSITIVE_EXCESS" in fp["failureCodes"]

    undef = v4.decide_statistic(_intervals(1000, 0, 0, 1000), 2000, spec)
    assert "UNDEFINED_FREQUENCY_EXCESS" in undef["failureCodes"] and undef["state"] == mc.FAIL

    none_measured = v4.decide_statistic([None] * 2000, 2000, spec)
    assert none_measured["state"] == mc.FAIL and none_measured["metrics"]["coverage"]["state"] == mc.INCONCLUSIVE


def test_run_status_is_inconclusive_for_a_small_complete_run():
    result = v4.run_calibration(_tiny_spec(replicates=3), formal=False)
    assert result["primaryStatus"] == mc.INCONCLUSIVE
    assert result["statusCounts"][mc.INCONCLUSIVE] == 1 and result["inconclusiveCells"]
    assert result["monteCarloDecision"]["passSideOneSidedAlpha"] == 0.025
    json.dumps(result, allow_nan=False)


# ---------------------------------------------------------------- protocol tampering (formal vs development)
def test_formal_mode_pins_every_scientific_choice():
    spec = _spec()
    v4.validate_spec(spec, formal=True)
    mutations = {
        "seed": lambda s: s.update(seed=1),
        "replicates": lambda s: s.update(simulationReplicates=2001),
        "mc confidence pass": lambda s: s["monteCarloDecision"].update(passSideOneSidedAlpha=0.05),
        "mc confidence fail": lambda s: s["monteCarloDecision"].update(failSideFamilywiseAlpha=0.2),
        "mc method": lambda s: s["monteCarloDecision"].update(intervalMethod="WALD"),
        "mc adjustment": lambda s: s["monteCarloDecision"].update(failSideAdjustment="NONE"),
        "mc decision count": lambda s: s["monteCarloDecision"].update(failSideDecisionCount=1),
        "coverage floor": lambda s: s["acceptance"].update(materialCoverageFloor=0.9),
        "false positive ceiling": lambda s: s["acceptance"].update(directionalFalsePositiveCeiling=0.1),
        "undefined ceiling": lambda s: s["acceptance"].update(undefinedFrequencyCeiling=0.2),
        "half width": lambda s: s["acceptance"].update(maximumMonteCarlo95HalfWidth=0.5),
        "u1": lambda s: s["intervalConstruction"].update(U1CriticalValue=60.0),
        "method": lambda s: s["intervalConstruction"].update(method="V3_SIGNAL_DATE"),
        "statistics": lambda s: s["statistics"].update(confirmatory=list(reversed(s["statistics"]["confirmatory"]))),
        "dgp parameter": lambda s: s["dgps"][0].update(sigmaShared=0.6),
        "dgp removed": lambda s: s["dgps"].pop(),
        "depths": lambda s: s["horizons"]["126"].update(calendarWeeks=[100, 624]),
    }
    for name, mutate in mutations.items():
        broken = copy.deepcopy(spec)
        mutate(broken)
        with pytest.raises(ValueError, match="INVALID_V4_PROTOCOL"):
            v4.validate_spec(broken, formal=True)
            raise AssertionError(f"mutation not refused in formal mode: {name}")


def test_development_mode_may_move_only_seed_replicates_and_registries():
    spec = _spec()
    dev = copy.deepcopy(spec)
    dev["seed"], dev["simulationReplicates"] = 7, 5
    v4.validate_spec(dev, formal=False)
    for mutate in (
        lambda s: s["monteCarloDecision"].update(passSideOneSidedAlpha=0.05),
        lambda s: s["acceptance"].update(materialCoverageFloor=0.9),
        lambda s: s["intervalConstruction"].update(U1CriticalValue=60.0),
        lambda s: s["intervalConstruction"].update(method="X"),
        lambda s: s["statistics"].update(descriptive=[]),
    ):
        broken = copy.deepcopy(dev)
        mutate(broken)
        with pytest.raises(ValueError, match="INVALID_V4_PROTOCOL"):
            v4.validate_spec(broken, formal=False)


def test_run_calibration_defaults_to_formal_and_refuses_a_modified_protocol():
    with pytest.raises(ValueError, match="INVALID_V4_PROTOCOL"):
        v4.run_calibration(_tiny_spec())


# ---------------------------------------------------------------- job status semantics
def test_inconclusive_result_is_a_complete_artifact_and_a_zero_exit(tmp_path):
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps(_tiny_spec()))
    out = tmp_path / "o.json"
    code, printed = _run(["--spec", str(spec_file), "--output", str(out),
                          "--development-smoke", "3", "--development-seed", "5"])
    assert code == 0
    artifact = json.loads(out.read_text())
    assert artifact["primaryStatus"] == "INCONCLUSIVE" and artifact["verdictAuthority"] == "NONE_DEVELOPMENT_ONLY"
    assert "INCONCLUSIVE" in printed


def test_workflow_only_fails_the_job_for_infrastructure_errors():
    text = WORKFLOW.read_text()
    verdict_step = text.split("- name: Record methodological verdict")[1].split("- name: Upload")[0]
    assert "exit 1" not in verdict_step and "::warning::" in verdict_step
    assert "INCONCLUSIVE" in verdict_step
    run_step = text.split("- name: Run synthetic-only calibration v4")[1].split("- name: Record")[0]
    assert "|| true" not in run_step  # exit status comes from the runner: 0 for any complete verdict, 1 for infra
    runner = Path("scripts/run_alpha_inference_calibration_v4.py").read_text()
    assert "return 1" in runner and runner.count("return 1") == 1
