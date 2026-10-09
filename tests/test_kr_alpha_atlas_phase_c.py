"""A-N synthetic scenarios run the SAME production research functions, never KR returns."""

from copy import deepcopy
from dataclasses import asdict
import json

import numpy as np
import pandas as pd
import pytest

from pipeline.kr_alpha_atlas_phase_c import contract, economics, executor, interactions, models, statistics
from pipeline.kr_alpha_atlas_phase_c.labels import Counters, build_labels, synthetic_permit
from pipeline.kr_alpha_atlas_phase_c.lifecycle import ordered_once
from pipeline.kr_alpha_atlas_phase_c.preflight import extract_exact, verify_git_inputs
from pipeline.kr_alpha_atlas_phase_c.synthetic import market, read_fixture, smoke, write_fixture


@pytest.fixture(scope="module")
def spec():
    return contract.load()


@pytest.fixture(scope="module")
def complete(spec):
    data = market(missing=True, names=32)
    result = executor.execute(data, spec, synthetic_permit(data))
    return data, result


@pytest.fixture
def small(spec):
    d = market(end="2014-12-30")
    c = Counters()
    book = build_labels(d, 21, spec["developmentCutoff"], synthetic_permit(d), c)
    return d, book, c


def feature(spec, fid):
    return next(f for f in spec["eligibleFeatures"] if f["featureId"] == fid)


def test_registration_calendar_and_actual_schema_metadata(spec):
    assert contract.validate(spec) == spec
    assert contract.calendar_facts(spec)["maturity"] == {
        "H21": "2026-08-07",
        "H63": "2026-06-12",
        "H126": "2026-03-06",
        "H252": "2025-08-29",
    }
    assert verify_git_inputs(contract.ROOT, spec)["realOutcomeReads"] == 0
    assert spec["compute"]["plannedPredictiveFits"] == 574
    assert len(spec["eligibleFeatures"]) == 38
    assert all(spec["alreadyTested"]["sealedReferences"].values())
    changed = deepcopy(spec)
    changed["linearModel"]["penalty"] = 0.5
    with pytest.raises(ValueError, match="MUTATED"):
        contract.validate(changed)


def test_A_true_standalone_direction(complete):
    _, result = complete
    r = result["level1"]["A10_residualMomentum126_H126"]
    assert r["statistics"]["tercileSpread"]["estimate"] > 0
    assert r["statistics"]["rankIC"]["mean"] > 0
    assert r["statistics"]["withinIndustryRankIC"]["mean"] > 0
    assert all(v > 0 for v in r["stability"]["halves"])


def test_B_noise_cannot_earn_independent_support(complete):
    _, result = complete
    r = result["level1"]["A04_return63d_H126"]
    assert abs(r["statistics"]["rankIC"]["mean"]) < 0.25
    assert result["verdicts"]["A04_return63d"]["verdict"] != "INDEPENDENT_DEVELOPMENT_SUPPORT"


def test_C_redundancy_and_D_incremental_known_information(small, spec):
    d, b, _ = small
    y = b.table.benchmarkRelative.to_numpy(float)
    # Known deterministic oracle forecasts, used only to test the comparison algebra.
    x = d.values.A05_relative126.to_numpy(float)
    z = d.values.D07_volumePriceAlignment.to_numpy(float)
    base = 0.00525 * x
    identical = base.copy()
    augmented = base + 0.0042 * z
    dates = sorted(d.rows.date[b.table.state.eq("VALID")].unique())
    redundant = statistics.matched_comparison(d, b, base, identical, dates, spec)
    incremental = statistics.matched_comparison(d, b, base, augmented, dates, spec)
    assert abs(redundant["pairedMseImprovement"]["estimate"]) < 1e-12
    assert incremental["pairedMseImprovement"]["estimate"] > 0
    assert incremental["pairedRankWeightedSpreadImprovement"]["estimate"] > 0
    # Independently verify paired demeaned-target MSE identity.
    first = dates[0]
    ids = d.rows.index[d.rows.date.eq(first) & b.table.state.eq("VALID")]
    centered = y[ids] - np.mean(y[ids])
    direct = np.mean((base[ids] - centered) ** 2 - (augmented[ids] - centered) ** 2)
    assert incremental["pairedMseImprovement"]["perDate"][0]["value"] == pytest.approx(direct)


def test_E_gross_opportunity_removed_by_costs(small, spec):
    d, b, _ = small
    date = b.table.loc[b.table.state.eq("VALID"), "date"].iloc[0]
    ids = d.rows.index[d.rows.date.eq(date)]
    # Same economic engine: make deterministic tiny stock opportunity, not new costs.
    for i in ids:
        entry = b.entry_positions[i]
        end = entry + b.horizon
        t = d.rows.loc[i, "ticker"]
        ratio = d.benchmark_close[entry : end + 1] / d.benchmark_close[entry]
        d.closes[t][entry : end + 1] = 100 * ratio * (1 + np.linspace(0, 0.0001, b.horizon + 1))
    b = build_labels(d, 21, spec["developmentCutoff"], synthetic_permit(d), Counters())
    block = economics.block(d, b, date, {int(ids[0]): 0.2}, "PASSIVE_BENCHMARK", spec)
    assert block["grossExcess"] > 0 and block["netExcess"] < 0
    policy = economics.summarize([block], spec)
    assert (
        executor.economic_verdict({"policies": {"fixture": policy}, "benchmarkClaimStatus": "VERIFIED"})
        == "NOT_ECONOMIC"
    )


def test_F_industry_exposure_is_not_stock_selection(small, spec):
    d, _, _ = small
    for i, t in enumerate(sorted(d.closes)):
        industry = i // 8
        d.closes[t] = 100 * np.cumprod(np.full(len(d.days), 1.00015 + 0.0001 * industry))
    b = build_labels(d, 21, spec["developmentCutoff"], synthetic_permit(d), Counters())
    date = b.table.loc[b.table.state.eq("VALID"), "date"].iloc[0]
    ids = d.rows.index[d.rows.date.eq(date) & d.rows.industry.eq("IND5")]
    block = economics.block(d, b, date, {int(ids[0]): 0.2, int(ids[1]): 0.2}, "PASSIVE_BENCHMARK", spec)
    assert block["attribution"]["B_industryAllocation"] > 0
    assert abs(block["attribution"]["C_stockSelection"]) < 1e-12
    assert block["grossReturn"] == pytest.approx(
        sum(v for k, v in block["attribution"].items() if k not in ("D_riskFactorExposure", "E_cost"))
    )


def test_G_outcome_missingness_and_I_unfair_population(small, spec):
    d, b, _ = small
    worst = min(d.closes, key=lambda t: d.closes[t][-1])
    d.closes[worst][100:140] = np.nan
    b = build_labels(d, 21, spec["developmentCutoff"], synthetic_permit(d), Counters())
    base = np.full(len(d.rows), 0.01)
    alt = base.copy()
    alt[d.rows.ticker.eq(worst)] = np.nan
    dates = sorted(d.rows.date[b.table.missingReason.ne("NOT_MATURED_BY_CUTOFF")].unique())
    r = statistics.matched_comparison(d, b, base, alt, dates, spec)
    assert r["identicalEvaluationPopulation"]
    assert r["preCommonBase"] > r["preCommonAlternative"]
    assert abs(r["pairedMseImprovement"]["estimate"]) < 1e-12
    assert r["commonObservations"] < len(d.rows)
    a = __import__("pipeline.kr_alpha_atlas_phase_c.labels", fromlist=["attrition"]).attrition(d, {21: b})[0]
    assert a["affectedSecurities"] == 1 and a["lostByYear"] and a["lostByIndustry"]


def test_H_unknown_terminal_never_fabricated_and_symmetric(small, spec):
    d, _, _ = small
    t = "SYN047"
    d.terminal_events[t] = {"lastTradingDate": "2013-07-01"}
    d.completeness[t] = {"exDateSemanticsResolved": "BLOCKED", "terminalConsiderationResolved": "BLOCKED"}
    b = build_labels(d, 21, spec["developmentCutoff"], synthetic_permit(d), Counters())
    held = b.table.ticker.eq(t)
    assert b.table.loc[held, "state"].eq("INVALID").all()
    assert b.table.loc[held, "gross"].isna().all()
    date = b.table.date.iloc[0]
    i = d.rows.index[d.rows.date.eq(date) & d.rows.ticker.eq(t)][0]
    assert economics.block(d, b, date, {int(i): 0.2}, "CASH", spec)["status"] == "BLOCKED"
    # A missing entry price is invalid, never a zero return.
    d2 = market(end="2013-06-28")
    d2.closes["SYN000"][3] = np.nan
    b2 = build_labels(d2, 21, spec["developmentCutoff"], synthetic_permit(d2), Counters())
    assert b2.table.iloc[0]["gross"] is None or pd.isna(b2.table.iloc[0]["gross"])


def test_J_future_filing_and_future_transform_refused(small, spec):
    d, b, _ = small
    fid = "C01_returnOnAssets"
    d.available.loc[0, fid] = "2026-09-15"
    with pytest.raises(ValueError, match="FILING_TIMESTAMP_LEAKAGE"):
        d.validate_features(spec)
    frame = pd.DataFrame({"x": [0.1, np.nan, 0.3, 0.9]})
    dates = np.array(["2013-01-04"] * 3 + ["2026-09-11"])
    tr = models.Transformer().fit(frame.iloc[:3], dates[:3])
    before = tr.audit()
    frame.loc[3, "x"] = 100000.0
    tr.transform(frame.iloc[3:])
    assert tr.audit() == before
    train, cutoff = models.training_indices(d, b, 2014, spec)
    if len(train):
        assert b.table.loc[train, "exit"].max() < cutoff


def test_K_regime_sign_reversal_is_visible(spec):
    d = market(end="2022-12-30", regime_reversal=True)
    books = {
        h: build_labels(d, h, spec["developmentCutoff"], synthetic_permit(d), Counters()) for h in spec["horizons"]
    }
    result = interactions.analyze(d, books, spec)
    x6 = next(v for k, v in result.items() if k.startswith("X6"))
    assert x6["regimeSlopes"]["NORMAL"]["mean"] > 0
    assert x6["regimeSlopes"]["STRESSED"]["mean"] < 0
    assert x6["p"] is None and "no CPI" in x6["claim"]


def test_L_source_blocked_and_all_blocked_interactions(small, spec):
    d, b, _ = small
    s = deepcopy(spec)
    for ix in s["interactions"]:
        ix["readiness"] = {"status": "SOURCE_BLOCKED", "reason": "SYNTHETIC_MISSING_SOURCE"}
    result = interactions.analyze(d, {h: b for h in s["horizons"]}, s)
    assert all(v["status"] == "BLOCKED" and v["p"] is None for v in result.values())
    assert all("G01_foreignNetBuying" not in v or v["status"] == "BLOCKED" for v in result.values())


def test_M_complete_determinism_full_schema_and_durable_bytes(complete, spec, tmp_path):
    d, first = complete
    second = executor.execute(d, spec, synthetic_permit(d))
    assert contract.canonical(first) == contract.canonical(second)
    assert first["evidenceClass"] == "SYNTHETIC_SOFTWARE_VALIDATION_ONLY"
    assert len(first["level1"]) == 73 and first["multiplicity"]["level2Slots"] == 30
    assert len(first["level3"]) == 6 and first["counters"]["realOutcomeReads"] == 0
    assert 0.44 < first["readiness"]["b4CompleteCaseShare"] < 0.45
    assert all(v["identicalEvaluationPopulation"] for h in first["level2"].values() for v in h["comparisons"].values())
    for audit in first["modelAudit"]:
        if audit["status"] == "FITTED":
            assert audit["lastTrainingTargetExit"] < audit["trainingCutoff"] < audit["firstEvaluationSignal"]
    executor.persist(first, tmp_path, {"mode": "SYNTHETIC"})
    executor.persist(second, tmp_path, {"mode": "SYNTHETIC"})
    assert json.loads((tmp_path / "result.json").read_text()) == first
    changed = deepcopy(first)
    changed["verdicts"].clear()
    with pytest.raises(ValueError):
        executor.validate_result(changed, spec)
    # A result cannot claim complete analysis after dropping a registered cell,
    # matched-population identity, control contrast or funded order accounting.
    ix = next(k for k in first["level3"] if k.startswith("X2"))
    economic = next(iter(first["level4"]))
    paths = [
        ("level2", "21", "comparisons", "ADD_A_H21"),
        ("level2", "21", "comparisons", "ADD_A_H21", "sampleSha256"),
        ("level3", ix, "contrast"),
        ("level4", economic, "policies", "DIAGNOSTIC_CASH", "blocks", 0, "executedWeights"),
    ]
    for path in paths:
        changed = deepcopy(first)
        target = changed
        for key in path[:-1]:
            target = target[key]
        del target[path[-1]]
        with pytest.raises(ValueError, match="RESULT_SCHEMA_REQUIRED"):
            executor.validate_result(changed, spec)


def test_N_permanent_lock_order_before_and_after_boundary():
    events = []
    locked = []
    failures = []

    def check():
        events.append("checks")
        if locked:
            raise ValueError("CONSUMED")

    def prepare_failure():
        events.append("prepare")
        raise ValueError("NETWORK_BEFORE_OUTCOME")

    def claim():
        events.append("lock")
        locked.append(True)
        return {"verified": True}

    def fail(error, receipt):
        failures.append((str(error), receipt))

    with pytest.raises(ValueError, match="NETWORK"):
        ordered_once(checks=check, prepare=prepare_failure, claim=claim, run=lambda d, r: None, on_failure=fail)
    assert not locked and not failures and events == ["checks", "prepare"]

    def run(data, receipt):
        events.append("OUTCOME_BOUNDARY")
        raise ValueError("AFTER_BOUNDARY")

    with pytest.raises(ValueError, match="AFTER"):
        ordered_once(checks=check, prepare=lambda: events.append("prepare"), claim=claim, run=run, on_failure=fail)
    assert locked and failures and events[-2:] == ["lock", "OUTCOME_BOUNDARY"]
    with pytest.raises(ValueError, match="CONSUMED"):
        ordered_once(checks=check, prepare=lambda: None, claim=claim, run=run, on_failure=fail)
    assert events.count("OUTCOME_BOUNDARY") == 1


def test_long_only_zero_investment_cost_schedule_and_bootstrap(small, spec):
    d, b, _ = small
    date = d.rows.date.iloc[0]
    ids = d.rows.index[d.rows.date.eq(date)].to_numpy()
    assert economics.select(d, ids, np.ones(len(ids)), np.zeros(len(d.rows)), "2013-01-07", "2013-02-07", spec) == {}
    block = economics.block(d, b, date, {}, "CASH", spec)
    assert block["grossReturn"] == 0 and block["selectedCount"] == 0 and block["unusedWeight"] == 1
    assert economics.stock_cost(spec, "2025-02-01", True) == pytest.approx(0.0026)
    assert economics.stock_cost(spec, "2013-02-01", True) == pytest.approx(0.0041)
    p = np.full(len(d.rows), 0.2)
    chosen = economics.select(d, ids, np.ones(len(ids)), p, "2013-01-07", "2013-02-07", spec)
    assert len(chosen) <= 5 and sum(chosen.values()) <= 1
    assert max(pd.Series([d.rows.loc[i, "industry"] for i in chosen]).value_counts()) <= 2
    assert smoke(spec)["realOutcomeReads"] == 0


def test_file_loader_checksum_and_missing_imports(small, spec, tmp_path):
    d, _, _ = small
    path = tmp_path / "market.json"
    write_fixture(d, path)
    loaded = read_fixture(path)
    loaded.validate_features(spec)
    assert loaded.closes.keys() == d.closes.keys()
    archive = tmp_path / "not-original.zip"
    archive.write_bytes(b"fake")
    with pytest.raises(ValueError, match="CHECKSUM"):
        extract_exact(archive, tmp_path / "input", spec["frozenArtifact"])
    changed = deepcopy(d)
    changed.source_identity = "REAL_SOURCE"
    with pytest.raises(ValueError, match="REAL_INPUT"):
        synthetic_permit(changed)
    assert asdict(Counters())["realModelFits"] == 0


def test_corrections_preserve_registered_slots_and_sn_limit():
    by = statistics.adjust({"a": 0.001, "blocked": None, "b": 0.2}, "BY")
    holm = statistics.adjust({"a": 0.01, "blocked": None, "b": 0.03}, "HOLM")
    assert by["blocked"] == 1 and holm["a"] == pytest.approx(0.03) and holm["b"] == pytest.approx(0.06)
    assert statistics.sn_tail(66.57) == pytest.approx(0.02501213046, abs=1e-10)
    assert statistics.sn_tail(100) > statistics.sn_tail(200) > 0
    assert statistics.adjust({}, "HOLM") == {}


def test_full_size_safe_synthetic_memory_and_masks(spec):
    # Exact 85,680-member-date workload, without reading or labelling historical data.
    d = market(end="2026-09-14", names=120, missing=True)
    ready = d.validate_features(spec)
    assert ready["rows"] == 85680 and ready["signalDates"] == 714
    b = build_labels(d, 21, spec["developmentCutoff"], synthetic_permit(d), Counters())
    assert b.table.shape[0] == 85680
    budget = executor.Budget(spec)
    budget.check()
    tiny = deepcopy(spec)
    tiny["compute"]["memoryBytes"] = 1
    with pytest.raises(RuntimeError, match="MEMORY"):
        executor.Budget(tiny).check()
    # No future coefficient reuse: no training means no predictions, never carry back.
    p, _, _ = models.predictions(
        market(end="2013-06-28"),
        build_labels(
            market(end="2013-06-28"),
            21,
            spec["developmentCutoff"],
            synthetic_permit(market(end="2013-06-28")),
            Counters(),
        ),
        spec,
        Counters(),
        synthetic_permit(market(end="2013-06-28")),
        executor.Budget(spec),
    )
    assert all(np.isnan(v).all() for v in p.values())


def test_real_permit_cannot_be_fabricated_and_imports():
    import importlib
    from pipeline.kr_alpha_atlas_phase_c.labels import formal_permit

    with pytest.raises(ValueError, match="PERMANENT_LOCK_REQUIRED"):
        formal_permit("REAL", {"ref": "refs/tags/kr-alpha-atlas-phase-c-v1-execution-lock", "verified": True})
    for path in (contract.ROOT / "pipeline/kr_alpha_atlas_phase_c").glob("*.py"):
        importlib.import_module("pipeline.kr_alpha_atlas_phase_c." + path.stem)


def test_duplicate_control_residual_and_empty_feature_group(small, spec, monkeypatch):
    d, b, _ = small
    reading = models.residual_and_slopes(d, b, feature(spec, "A12_momentumPersistence"), spec)
    assert reading["residualized"]["statistics"]["tercileSpread"]["nDates"] == 0
    monkeypatch.setattr(models, "model_groups", lambda spec: {21: {"B4_COMBINED_SIMPLE": [], "FULL": []}})
    short = market(end="2016-12-30")
    book = build_labels(short, 21, spec["developmentCutoff"], synthetic_permit(short), Counters())
    p, audit, _ = models.predictions(short, book, spec, Counters(), synthetic_permit(short), executor.Budget(spec))
    assert all(np.isnan(v).all() for v in p.values())
    assert any(a["status"] == "BLOCKED_EMPTY_FEATURE_GROUP" for a in audit)


def test_invalid_outcome_name_still_forecast(small, spec):
    d = market(end="2016-12-30")
    t = "SYN047"
    d.completeness[t] = {"exDateSemanticsResolved": "BLOCKED"}
    b = build_labels(d, 21, spec["developmentCutoff"], synthetic_permit(d), Counters())
    p, _, _ = models.predictions(d, b, spec, Counters(), synthetic_permit(d), executor.Budget(spec))
    ids = d.rows.index[d.rows.ticker.eq(t) & d.rows.date.str.startswith("2016")]
    assert len(ids) > 0 and b.table.loc[ids, "state"].eq("INVALID").all()
    assert np.isfinite(p["B4_COMBINED_SIMPLE"][ids]).all()


def test_all_registered_economic_policies_and_net_paths(small, spec):
    d = market(end="2016-12-30")
    b = build_labels(d, 21, spec["developmentCutoff"], synthetic_permit(d), Counters())
    forecasts = {"ADD_A": np.full(len(d.rows), 0.02)}
    result = economics.evaluate(d, b, feature(spec, "A10_residualMomentum126"), forecasts, spec)
    assert len(result["policies"]) == 12
    assert any(p["status"] != "BLOCKED" for p in result["policies"].values())
    for name, p in result["policies"].items():
        if p["status"] == "BLOCKED":
            continue
        assert p["descriptiveBootstrap"]["draws"] == 499
        assert p["concentrationMaximum"] <= 0.2 + 1e-12 if name.startswith("SLOTS") else True
        for block in p["blocks"]:
            assert block["entryCashWeight"] >= 0
            assert sum(block["executedWeights"].values()) + block["executedFallbackWeight"] + block["entryCashWeight"] + block["entryFeeWeight"] == pytest.approx(1)
            assert block["dailyNetWealth"][-1] - 1 == pytest.approx(block["netReturn"])
            assert np.prod(1 + np.asarray(block["dailyBenchmarkNetReturns"])) - 1 == pytest.approx(
                block["benchmarkNetReturn"]
            )
            if name.startswith("SLOTS"):
                assert len(block["weights"]) <= 5 and max(block["industryWeights"].values(), default=0) <= 0.4 + 1e-12
        capital = spec["economics"]["capitalKrw"]
        for block in p["blocks"]:
            assert block["entryCapitalKrw"] == pytest.approx(capital)
            capital *= 1 + block["netReturn"]


def test_fully_funded_fees_signal_costs_and_unpriceable_nav(spec):
    d = market(end="2016-12-30")
    b = build_labels(d, 21, spec["developmentCutoff"], synthetic_permit(d), Counters())
    date = sorted(d.rows.date.unique())[0]
    ids = d.rows.index[d.rows.date.eq(date)].to_numpy(int)
    weights = {int(i): 0.2 for i in ids[:5]}
    funded = economics.block(d, b, date, weights, "CASH", spec)
    assert funded["entryCashWeight"] == pytest.approx(0)
    assert sum(funded["executedWeights"].values()) < 1
    assert funded["dailyNetWealth"][0] == pytest.approx(1 - funded["entryFeeWeight"])
    prediction = np.full(len(d.rows), 0.0077)
    early = economics.select(d, ids, np.ones(len(ids)), prediction, "2013-01-07", "2013-02-07", spec)
    late = economics.select(d, ids, np.ones(len(ids)), prediction, "2013-01-07", "2025-02-07", spec)
    assert early == late == {}  # 2013 signal's round-trip hurdle is 82bp.
    b.table.loc[d.rows.ticker.eq("SYN000"), "state"] = "INVALID"
    forecasts = {"ADD_A": np.full(len(d.rows), 0.02)}
    f = {**feature(spec, "A10_residualMomentum126"), "expectedDirection": -1}
    result = economics.evaluate(d, b, f, forecasts, spec)
    p = result["policies"]["DIAGNOSTIC_CASH"]
    assert p["status"] == result["pairedPolicyComparisonStatus"] == "BLOCKED"
    assert p["blocks"][0]["reason"] == "SELECTED_OR_INDUSTRY_REFERENCE_UNPRICEABLE"
    assert all(v["reason"] == "UNPRICED_PRIOR_NAV" for v in p["blocks"][1:])


def test_actual_selected_source_file_schemas_without_labels(spec):
    from pipeline.kr_alpha_atlas_phase_c.preflight import verify_source_schema_samples

    report = verify_source_schema_samples(contract.ROOT, spec)
    assert len(report["selectedSourceSchemas"]) == 4
    assert report["realLabels"] == report["realModelFits"] == report["realOutcomeReads"] == 0


def test_registered_conditional_baskets_and_control_not_doubled(spec):
    d = market(end="2018-12-28")
    b = build_labels(d, 126, spec["developmentCutoff"], synthetic_permit(d), Counters())
    forecasts = {"FULL": np.full(len(d.rows), 0.03)}
    ranks = statistics.percentiles(d)
    for ix in spec["interactions"]:
        if not ix["interactionId"].startswith(("X1", "X2", "X5")):
            continue
        component = next(f for f in spec["eligibleFeatures"] if f["featureId"] in ix["features"])
        result = economics.evaluate(d, b, component, forecasts, spec, interaction=ix)
        assert result["interactionId"] == ix["interactionId"] and len(result["policies"]) == 12
        for p in result["policies"].values():
            for block in p["blocks"]:
                if block["status"] == "BLOCKED":
                    continue
                indices = d.rows.index[d.rows.date.eq(block["date"]) & d.rows.ticker.isin(block["weights"])]
                if ix["interactionId"].startswith("X1"):
                    assert d.rows.loc[indices, "b08Confirmed"].eq(1).all()
                elif ix["interactionId"].startswith("X2"):
                    assert ranks.loc[indices, ix["features"][1]].le(1 / 3).all()
                else:
                    assert ranks.loc[indices, ix["features"][0]].le(1 / 3).all()
    books = {
        h: build_labels(d, h, spec["developmentCutoff"], synthetic_permit(d), Counters()) for h in spec["horizons"]
    }
    result = interactions.analyze(d, books, spec)
    for key, r in result.items():
        if key.startswith(("X1", "X3")):
            assert r["contrast"]["estimate"] == r["pairedVersusNegativeControl"]["estimate"]
