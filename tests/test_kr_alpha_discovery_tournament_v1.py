"""kr-alpha-discovery-tournament-v1: registries, representations, nested walk-forward isolation, targets, models, calibration, uncertainty,
multiplicity statistics and the frozen verdict. Synthetic data only; no market data is read."""
from __future__ import annotations

import os

os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from pipeline import kr_alpha_tournament as T  # noqa: E402
from pipeline import kr_alpha_tournament_evaluation as E  # noqa: E402
from pipeline import kr_alpha_tournament_features as F  # noqa: E402
from pipeline import kr_alpha_tournament_models as M  # noqa: E402
from pipeline import kr_alpha_tournament_study as ST  # noqa: E402
from pipeline import kr_alpha_tournament_walkforward as W  # noqa: E402
from pipeline import replay_calendar as RC  # noqa: E402


@pytest.fixture(scope="module")
def synthetic():
    return ST.run_synthetic(ST.SyntheticWorld(names=24, industries=4), counters={})


# --------------------------------------------------------------------------- #
# Registries and the trial ledger
# --------------------------------------------------------------------------- #
def test_registry_is_closed_bounded_and_counted():
    reg = T.candidate_registry()
    assert len(reg) == 120 and len({c["id"] for c in reg}) == 120
    ledger = T.trial_ledger(9)
    assert ledger["fittedConfigurations"] == 120 and ledger["totalEffectiveTrials"] == 123
    assert ledger["modelFamilies"] == 6 <= 6 and ledger["fittedModelFamilies"] == 5
    assert ledger["hyperparameterConfigurations"] == 11 and ledger["targetArchitectures"] == 4 and ledger["recencySchemes"] == 3
    assert ledger["fittedModelsAcrossOuterFolds"] == 120 * 9 * 4
    assert {c["family"] for c in reg} == set(T.FITTED_FAMILIES)
    assert {c["target"] for c in reg if c["family"] == "LEARNING_TO_RANK"} == set(T.RANKER_TARGETS)


def test_only_ready_information_enters_and_every_feature_belongs_to_a_usable_family():
    usable = {f for fam in T.INFORMATION_REGISTRY.values() if fam["class"] in T.USABLE_INFORMATION_CLASSES for f in fam["fields"]}
    assert set(T.STOCK_FEATURES) | set(T.INDUSTRY_FEATURES) | set(T.MARKET_FEATURES) <= usable
    for name in ("KR_INVESTOR_FLOW", "KR_SHORT_SELLING", "DART_OWNERSHIP_5PCT", "MARKET_STATE_MACRO_FRED_VIX", "KR_MACRO_ECOS"):
        assert T.INFORMATION_REGISTRY[name]["class"] not in T.USABLE_INFORMATION_CLASSES


def test_duplicate_research_audit_states_both_what_differs_and_what_does_not():
    audit = T.duplicate_research_audit()
    assert set(audit["materialDifferences"]) == {"informationRepresentation", "targets", "modelSelectionArchitecture", "objective"}
    assert "NO genuinely new raw information" in audit["notDifferent"]
    assert "regional-alpha-model-v1" in audit["closedPredecessors"]


def test_no_hand_weighted_factor_blend_exists():
    for name in dir(T):
        assert "FACTOR_WEIGHT" not in name.upper()


# --------------------------------------------------------------------------- #
# Representations (signal-time, per-date, order-independent)
# --------------------------------------------------------------------------- #
def _raw(n_dates=3, n=30, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for d in range(n_dates):
        for i in range(n):
            row = {"date": f"2020-01-{d + 2:02d}", "ticker": f"T{i:03d}", "industry": f"I{i % 5}", "industryEligible": True}
            row.update({f: float(rng.normal()) for f in T.STOCK_FEATURES})
            row.update({"ind_" + f: float(rng.normal() + i % 5) for f in T.INDUSTRY_FEATURES})
            row.update(marketTrendAdverse=1.0, marketVol63=0.2)
            rows.append(row)
    return pd.DataFrame(rows)


def test_representations_do_not_depend_on_row_order_or_other_dates():
    raw = _raw()
    a = F.represent(raw)
    b = F.represent(raw.sample(frac=1.0, random_state=3))
    pd.testing.assert_frame_equal(a, b)
    one = F.represent(raw[raw.date == "2020-01-02"])
    cols = [c for c in one if c.startswith(("z_", "p_", "w_", "i_"))]
    pd.testing.assert_frame_equal(one[cols].reset_index(drop=True), a[a.date == "2020-01-02"][cols].reset_index(drop=True))


def test_robust_z_is_clipped_and_missing_stays_missing():
    x = np.r_[np.arange(20, dtype=float), 1e9, np.nan]
    z = F.robust_z(x)
    assert np.nanmax(z) == T.ROBUST_Z_CLIP and np.isnan(z[-1])
    assert np.isnan(F.robust_z(np.arange(5, dtype=float))).all()


def test_linear_design_carries_missingness_and_registered_interactions_only():
    raw = _raw()
    raw.loc[0, "bookToMarketProxy"] = np.nan
    rep = F.represent(raw)
    X, names = F.linear_design(rep)
    assert np.isfinite(X).all() and len(names) == len(set(names))
    assert X[0, names.index("m_bookToMarketProxy")] == 1.0 and X[0, names.index("z_bookToMarketProxy")] == 0.0
    assert sum("*" in n for n in names) == len(T.INTERACTIONS)


def test_derived_price_features_need_full_windows():
    close = np.linspace(100, 120, 253)
    out = F.derived_price_features(close, np.linspace(100, 110, 253))
    assert all(v is not None for v in out.values())
    short = F.derived_price_features(close[-30:], close[-30:])
    assert short["ret21"] is not None and short["ret63"] is None and short["beta252"] is None
    gap = close.copy()
    gap[-10] = np.nan
    assert F.derived_price_features(gap, close)["ret63"] is None


def test_loo_industry_momentum_excludes_the_stock_and_refuses_partial_peers():
    trail = {"A": 0.10, "B": 0.0, "C": 0.04}
    caps = {"A": 1e12, "B": 1.0, "C": 3.0}
    assert F.loo_industry_momentum("A", ["B", "C"], trail, caps) == pytest.approx(0.10 - 0.03)
    assert F.loo_industry_momentum("A", ["B", "D"], trail, caps) is None


# --------------------------------------------------------------------------- #
# Calendar, folds, purge and embargo
# --------------------------------------------------------------------------- #
def test_outer_fold_cutoff_is_the_first_anchor_signal_of_the_year():
    anchors = [("2017-12-20", "2017-12-15"), ("2018-01-19", "2018-01-12"), ("2018-02-20", "2018-02-16"), ("2019-01-18", "2019-01-11")]
    folds = W.outer_folds(anchors)
    assert [(f["year"], f["cutoff"], len(f["anchors"])) for f in folds] == [(2018, "2018-01-12", 2), (2019, "2019-01-11", 1)]


def _calendar_world(n_dates=200):
    days = [str(d.date()) for d in RC.sessions("2014-01-01", "2020-12-31", "KR")]
    cal = W.Calendar(days)
    dates = days[300:300 + 5 * n_dates:5]
    rows = pd.DataFrame([(d, t) for d in dates for t in ("A", "B")], columns=["date", "ticker"])
    labels = pd.DataFrame({"exitDate": [cal.exit(d, T.PRIMARY_HORIZON) for d in rows.date], "eligible": True})
    return cal, rows, labels


def test_training_mask_is_strictly_before_the_cutoff():
    cal, rows, labels = _calendar_world()
    cutoff = rows.date.iloc[len(rows) // 2]
    mask = W.training_mask(labels, cutoff)
    assert (labels.exitDate[mask] < cutoff).all() and (labels.exitDate[~mask] >= cutoff).all()


def test_inner_blocks_purge_overlapping_labels_and_apply_the_embargo():
    cal, rows, labels = _calendar_world()
    dates = rows.date.to_numpy()
    train = W.training_mask(labels, "2020-12-01")
    blocks = W.inner_blocks(dates, train, labels, cal)
    assert len(blocks) == T.INNER_BLOCKS
    for b in blocks:
        if b["status"] == "EMPTY":
            continue
        tr = b["train"]
        assert (labels.exitDate[tr] < b["firstEntry"]).all(), "an inner training label overlaps its validation block"
        assert (dates[tr] <= b["embargoLimit"]).all()
        assert not (tr & b["valid"]).any()
        assert set(dates[b["valid"]]) <= set(dates[train])


def test_embargo_binds_when_the_label_horizon_is_short():
    days = [str(d.date()) for d in RC.sessions("2016-01-01", "2019-12-31", "KR")]
    cal = W.Calendar(days)
    dates = np.array(days[100:700])
    labels = pd.DataFrame({"exitDate": [cal.days[cal.index[d] + 2] for d in dates], "eligible": True})
    train = np.ones(len(dates), bool)
    for b in W.inner_blocks(dates, train, labels, cal):
        assert (dates[b["train"]] <= b["embargoLimit"]).all()
        gap = cal.index[b["firstSignal"]] - max(cal.index[d] for d in dates[b["train"]])
        assert gap >= T.EMBARGO_SESSIONS


def test_econ_dates_do_not_overlap():
    days = [str(d.date()) for d in RC.sessions("2016-01-01", "2017-12-31", "KR")]
    cal = W.Calendar(days)
    chosen = W.econ_dates(days[100:300:5], cal)
    for a, b in zip(chosen, chosen[1:]):
        assert cal.entry(b) >= cal.exit(a, T.INNER_BLOCK_HORIZON)


# --------------------------------------------------------------------------- #
# Targets and label endpoints
# --------------------------------------------------------------------------- #
def test_label_endpoints_follow_target_from_sessions_semantics():
    world = ST.SyntheticWorld(names=24, industries=4, end="2018-12-28")
    date = world.weekly[10]
    entry, exit_, r, status = ST.forward_return(world.close_at, world.calendar, world.tickers[0], date, T.PRIMARY_HORIZON, world.through)
    pos = world.calendar.index[date]
    assert entry == world.days[pos + 1] and exit_ == world.days[pos + 1 + T.PRIMARY_HORIZON] and status == "MATURED"
    assert r == pytest.approx(world.closes[world.tickers[0]][exit_] / world.closes[world.tickers[0]][entry] - 1)
    late = world.weekly[-1]
    assert ST.forward_return(world.close_at, world.calendar, world.tickers[0], late, T.PRIMARY_HORIZON, world.through)[3] == "PENDING"


def test_targets_are_defined_on_eligible_rows_and_never_zero_filled():
    world = ST.SyntheticWorld(names=60, industries=4, end="2018-06-29")
    rows = world.signal_rows()
    dates = sorted(rows.date.unique())[:3]
    rows = rows[rows.date.isin(dates)]
    bad = {(dates[0], world.tickers[0])}
    labels = ST.build_labels(rows, world.calendar, world.close_at, world.through, ineligible=bad)
    first = labels[labels.date == dates[0]].set_index("ticker")
    assert not first.loc[world.tickers[0], "eligible"] and np.isnan(first.loc[world.tickers[0], "yEcon"])
    el = first[first.eligible]
    assert np.allclose(el["C_CROSS_SECTIONAL_RANK"].sort_values().to_numpy() + 0.5, (np.arange(len(el)) + 0.5) / len(el))
    assert set(el["D_TOP_QUINTILE_EVENT"].unique()) <= {0.0, 1.0}
    assert el["A_MAGNITUDE_VS_SAME_DATA_UNIVERSE"].notna().all()
    same = el.industry == world.industry[world.tickers[0]]
    assert el.loc[same, "B_RESIDUAL_VS_LOO_INDUSTRY"].isna().all(), "a withheld peer must make the LOO industry residual missing (sealed rule)"
    assert np.isfinite(el.loc[~same, "B_RESIDUAL_VS_LOO_INDUSTRY"]).all()
    assert np.allclose(el["yEcon"], el["stock"] - (el["stock"] - el["yEcon"]).iloc[0])


def test_a_pending_label_never_enters_training():
    world = ST.SyntheticWorld(names=24, industries=4, end="2018-06-29")
    rows = world.signal_rows()
    labels = ST.build_labels(rows[rows.date == world.weekly[-1]], world.calendar, world.close_at, world.through)
    assert not labels.eligible.any() and labels.exitDate.isna().all()


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
def _xy(n=1200, p=8, seed=1):
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(n, p))
    y = X[:, 0] * 0.5 + rng.normal(size=n) * 0.5
    dates = np.repeat(np.arange(n // 40).astype(str), 40)
    return X, y, np.ones(n), dates


@pytest.mark.parametrize("candidate", [c for c in ST.synthetic_registry()])
def test_every_family_is_deterministic_and_learns_a_planted_signal(candidate):
    X, y, w, dates = _xy()
    a = M.fit_candidate(candidate, X, y, w, dates).predict(X)
    b = M.fit_candidate(candidate, X, y, w, dates).predict(X)
    assert np.array_equal(a, b)
    assert M.spearman(a, X[:, 0]) > 0.5


def test_recency_weights_are_date_balanced_and_refuse_future_dates():
    dates = np.array(["2017-01-06"] * 4 + ["2019-01-04"] * 2)
    w = M.recency_weights(dates, "2020-01-01", "NO_DECAY")
    assert w[:4].sum() == pytest.approx(w[4:].sum())
    h = M.recency_weights(dates, "2020-01-01", "HALF_LIFE_2Y")
    assert h[0] < h[-1]
    with pytest.raises(ValueError, match="AFTER_THE_CUTOFF"):
        M.recency_weights(dates, "2018-01-01", "HALF_LIFE_5Y")


def test_ranking_pairs_do_not_depend_on_row_order():
    X, y, w, dates = _xy()
    a = M.ranking_pairs(X, y, dates, w, 20)
    perm = np.random.default_rng(0).permutation(len(y))
    b = M.ranking_pairs(X[perm], y[perm], dates[perm], w[perm], 20)
    assert a[0].shape == b[0].shape and np.allclose(np.sort(a[0], axis=0), np.sort(b[0], axis=0))


# --------------------------------------------------------------------------- #
# Calibration and uncertainty
# --------------------------------------------------------------------------- #
def test_calibration_shrinks_never_credits_carry_and_cannot_create_alpha():
    rng = np.random.default_rng(2)
    dates = np.repeat(np.arange(60).astype(str), 50)
    s = np.tile((np.arange(50) + 0.5) / 50, 60)
    y = 0.05 + 0.04 * (s - 0.5) + rng.normal(0, 0.05, len(s))
    cal = M.calibrate(dates, s, y)
    assert 0 < cal["bStar"] <= cal["b"] and cal["credited"] == 0.0 and cal["carry"] > 0
    mu, sd = M.apply_calibration(cal, s)
    assert np.max(np.abs(mu)) <= cal["bStar"] / 2 + 1e-12 and (sd >= 0).all()
    flat = M.calibrate(dates, s, rng.normal(0, 0.05, len(s)) - 0.02 * (s - 0.5))
    assert flat["bStar"] == 0.0


def test_lagging_universe_is_charged_not_credited():
    dates = np.repeat(np.arange(20).astype(str), 30)
    s = np.tile((np.arange(30) + 0.5) / 30, 20)
    cal = M.calibrate(dates, s, -0.03 + 0.0 * s)
    assert cal["credited"] == pytest.approx(-0.03)


def test_contraction_is_a_contraction_and_disagreement_shrinks():
    mu = np.array([[0.02, -0.01, 0.0], [0.02, 0.01, 0.0]])
    sd = np.zeros_like(mu)
    c = M.contract(mu, sd)
    assert c["kappa"][0] == 1.0 and c["muPost"][1] == 0.0 and c["muPost"][2] == 0.0
    assert np.all(np.abs(c["muPost"]) <= np.abs(c["mu"]))
    noisy = M.contract(mu, sd + 0.05)
    assert np.all(np.abs(noisy["muPost"]) <= np.abs(c["muPost"]) + 1e-15)


def test_contraction_property_holds_on_random_inputs():
    rng = np.random.default_rng(12)
    for _ in range(200):
        k, n = int(rng.integers(1, 4)), 30
        c = M.contract(rng.normal(0, 0.03, (k, n)), np.abs(rng.normal(0, 0.02, (k, n))))
        assert np.all(np.abs(c["muPost"]) <= np.abs(c["mu"]) + 1e-15) and np.all(c["muPost"] * c["mu"] >= 0)
        assert np.all((c["kappa"] >= 0) & (c["kappa"] <= 1))


# --------------------------------------------------------------------------- #
# Selection rule
# --------------------------------------------------------------------------- #
def test_selection_keeps_one_per_family_ranks_by_economics_and_can_return_passive():
    results = [{"id": "SHRUNK_LINEAR|a", "family": "SHRUNK_LINEAR", "survives": True, "economicScore": 0.03},
               {"id": "SHRUNK_LINEAR|b", "family": "SHRUNK_LINEAR", "survives": True, "economicScore": 0.05},
               {"id": "SHALLOW_TREE|a", "family": "SHALLOW_TREE", "survives": True, "economicScore": 0.04},
               {"id": "LATENT_FACTOR|a", "family": "LATENT_FACTOR", "survives": False, "economicScore": 0.09},
               {"id": "LEARNING_TO_RANK|a", "family": "LEARNING_TO_RANK", "survives": True, "economicScore": 0.01},
               {"id": "SPARSE_LINEAR|a", "family": "SPARSE_LINEAR", "survives": True, "economicScore": 0.001}]
    assert W.select_ensemble(results) == ["SHRUNK_LINEAR|b", "SHALLOW_TREE|a", "LEARNING_TO_RANK|a"]
    assert W.select_ensemble([dict(r, survives=False) for r in results]) == []


# --------------------------------------------------------------------------- #
# Inner-vs-outer isolation and the whole synthetic tournament
# --------------------------------------------------------------------------- #
def test_outer_fold_ignores_labels_that_exit_on_or_after_its_cutoff():
    world = ST.SyntheticWorld(names=24, industries=4, end="2019-06-28")
    rows = world.signal_rows()
    data = W.prepare_data(F.represent(rows))
    raw = ST.build_labels(rows, world.calendar, world.close_at, world.through)
    labels = W.align_labels(data, raw)
    fold = W.outer_folds(world.anchors)[0]
    registry = ST.synthetic_registry()[:2]
    risk = world.risk()
    log_a, anchors_a = W.run_outer_fold(fold, data, labels, registry, risk, world.calendar)
    poisoned = labels.copy()
    future = poisoned.exitDate.fillna("9999").astype(str) >= fold["cutoff"]
    rng = np.random.default_rng(9)
    for col in ("yEcon", *T.TARGET_ORDER, "r21Stock"):
        poisoned.loc[future, col] = rng.normal(size=int(future.sum())) * 10
    log_b, anchors_b = W.run_outer_fold(fold, data, poisoned, registry, risk, world.calendar)
    assert log_a["ensemble"] == log_b["ensemble"]
    for day in anchors_a:
        for key in ("mu", "muPost"):
            if key in anchors_a[day]:
                assert np.array_equal(anchors_a[day][key], anchors_b[day][key])
        assert np.array_equal(anchors_a[day]["dflWeights"], anchors_b[day]["dflWeights"])


def test_synthetic_tournament_runs_end_to_end_and_is_deterministic(synthetic):
    again = ST.run_synthetic(ST.SyntheticWorld(names=24, industries=4), counters={})
    from pipeline import kr_alpha_tournament_execution as X
    assert X.digest(X.json_safe(synthetic["result"])) == X.digest(X.json_safe(again["result"]))
    assert synthetic["result"]["verdict"]["code"] in "ABCDE"
    assert all(synthetic["result"]["complete"].values())


def test_synthetic_tournament_reports_breadth_and_every_translator(synthetic):
    paths = synthetic["result"]["paths"]
    assert {k.split(":")[0] for k in paths} == set(ST.TRANSLATORS)
    assert paths["BASELINE_0_PASSIVE:BASE"]["meanActiveNames"] == 0.0
    for k, v in paths.items():
        assert v["maxActiveWeight"] <= T.PORTFOLIO["singleNameCap"] + 1e-9


# --------------------------------------------------------------------------- #
# Multiplicity statistics
# --------------------------------------------------------------------------- #
def test_bootstrap_is_seeded_and_brackets_the_mean():
    rng = np.random.default_rng(4)
    diff = rng.normal(0.0002, 0.005, 1500)
    a, b = E.moving_block_bootstrap(diff), E.moving_block_bootstrap(diff)
    assert a == b and a["lower95"] < np.mean(diff) * 252 * 100 < a["upper95"]


def test_deflated_sharpe_falls_with_more_trials():
    rng = np.random.default_rng(5)
    x = rng.normal(0.01, 0.03, 100)
    trials = rng.normal(0, 0.1, 120)
    few, many = E.deflated_sharpe(x, trials, 2), E.deflated_sharpe(x, trials, 1000)
    assert few["dsr"] > many["dsr"]


def test_pbo_separates_a_persistent_winner_from_anti_persistent_configurations():
    rng = np.random.default_rng(6)
    noise = rng.normal(0, 0.02, (96, 30))
    planted = noise.copy()
    planted[:, 0] += 0.03
    assert E.pbo_cscv(planted)["pbo"] < 0.1
    groups = np.array_split(np.arange(96), T.PBO_GROUPS)
    anti = rng.normal(0, 0.002, (96, 30))
    for j in range(30):
        good = rng.permutation(T.PBO_GROUPS)[:T.PBO_GROUPS // 2]
        for g, idx in enumerate(groups):
            anti[idx, j] += 0.01 if g in good else -0.01
    assert E.pbo_cscv(anti)["pbo"] > 0.9
    assert E.pbo_cscv(noise[:, :1])["status"] == "TOO_SMALL"


def test_spa_rejects_a_real_edge_and_not_noise():
    rng = np.random.default_rng(7)
    noise = rng.normal(0, 0.02, (110, 10))
    assert E.spa_test(noise)["pValue"] > 0.05
    edge = noise.copy()
    edge[:, 3] += 0.015
    assert E.spa_test(edge)["pValue"] < 0.05
    assert E.spa_test(np.zeros((110, 3)))["pValue"] == 1.0


# --------------------------------------------------------------------------- #
# The frozen verdict
# --------------------------------------------------------------------------- #
def _evidence(**kw):
    base = {"integrity": {"pathsComplete": True, "identityUnchanged": True, "signalCoveragePercent": 100.0}, "gPp": 2.0, "bootstrapLower": 0.2,
            "gCostX2Pp": 1.0, "periodsPositive": 4, "gLeaveLargestOutPp": 0.5, "dsr": 0.97, "spaP": 0.01, "pbo": 0.2, "icLower95": 0.01}
    base.update(kw)
    return base


def test_verdict_hierarchy_is_exactly_as_registered():
    assert E.verdict(_evidence())["code"] == "A"
    assert E.verdict(_evidence(dsr=0.5))["code"] == "B"
    assert E.verdict(_evidence(gPp=0.0, icLower95=0.02))["code"] == "C"
    d = E.verdict(_evidence(gPp=-1.0, icLower95=-0.01))
    assert d["code"] == "D" and d["verdict"] == "INFORMATION_LIMITED" and "closes permanently" in d["nextStep"]
    assert E.verdict(_evidence(integrity={"pathsComplete": False, "identityUnchanged": True, "signalCoveragePercent": 100.0}))["code"] == "E"
    assert E.verdict(_evidence(integrity={"pathsComplete": True, "identityUnchanged": True, "signalCoveragePercent": 79.9}))["code"] == "E"


def test_missing_evidence_never_passes_a_check():
    out = E.verdict(_evidence(dsr=None, pbo=None))
    assert out["code"] == "B" and not out["checks"]["dsr"] and not out["checks"]["pbo"]
    assert E.verdict(_evidence(gPp=None, icLower95=None))["code"] == "D"
