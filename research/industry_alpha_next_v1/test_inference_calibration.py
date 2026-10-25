"""Synthetic-only checks of the inference calibration machinery. No market data is read anywhere."""
import json

import numpy as np
import pytest

from . import evaluate as E
from . import inference_calibration as C
from . import study as S


def protocol():
    return C.load_protocol(formal=False)


def test_frozen_protocol_digest_and_registered_constants():
    p = C.load_protocol(formal=True)
    assert p["frozenDigest"] == C.protocol_digest(p)
    assert p["registeredTest"]["bootstrap"] == S.BOOTSTRAP
    assert set(p["candidates"]) == set(C.CANDIDATES)
    assert p["seeds"]["formal"] != p["seeds"]["development"]


def test_a_tampered_protocol_is_refused(tmp_path):
    p = C.load_protocol(formal=True)
    p["decisionRule"]["sizeCeiling"] = 0.2
    path = tmp_path / "p.json"
    path.write_text(json.dumps(p))
    with pytest.raises(ValueError, match="PROTOCOL_DIGEST_MISMATCH"):
        C.load_protocol(path, formal=True)


def test_limit_critical_values_reproduce_the_repository_sn_constant():
    cv = C.limit_critical_values(paths=20_000, length=500, seed=3)
    assert abs(cv["snSquaredExceeds66_57"] - 0.025) < 0.006
    assert abs(cv["kvbOneSided95"] - 3.76) < 0.25 and abs(cv["snOneSided95"] - 5.34) < 0.35


def test_the_registered_test_is_called_not_copied(monkeypatch):
    seen = []
    monkeypatch.setattr(E, "moving_block_bootstrap_p", lambda d: seen.append(len(d)) or 0.5)
    out = C.decisions(np.random.default_rng(0).normal(size=40), protocol(), 126)
    assert seen == [40] and out["C0_REGISTERED_MBB"]["p"] == 0.5


def test_circular_bootstrap_draws_every_observation_equally():
    idx = C._circular_indices(48, 12, 4000, np.random.default_rng(1))
    freq = np.bincount(idx.ravel(), minlength=48) / idx.size * 48
    assert freq.min() > 0.9 and freq.max() < 1.1


def test_every_candidate_rejects_a_large_positive_mean_and_none_a_negative_one():
    rng = np.random.default_rng(2)
    up = C.decisions(rng.normal(loc=2.0, size=60), protocol(), 126)
    down = C.decisions(rng.normal(loc=-2.0, size=60), protocol(), 126)
    assert all(v["reject"]["0.05"] for v in up.values())
    assert not any(v["reject"]["0.05"] for v in down.values())


def test_batch_means_is_undefined_below_two_batches_and_never_rejects():
    p, q = C.batch_means_p(np.ones(20) + np.arange(20) * 0.01, 252)
    assert p is None and q == 1
    out = C.decisions(np.random.default_rng(3).normal(size=20), protocol(), 252)
    assert out["C6_BATCH_MEANS_T"]["undefined"] and not out["C6_BATCH_MEANS_T"]["reject"]["0.05"]


def test_bartlett_lrv_matches_the_sample_variance_at_lag_zero():
    x = np.random.default_rng(4).normal(size=(3, 50))
    assert np.allclose(C.bartlett_lrv(x, 0), x.var(axis=1))


def test_world_reproduces_the_real_calendar_support_and_has_no_future_feature():
    P = protocol()
    rng = np.random.default_rng(np.random.SeedSequence([P["seeds"]["development"], 0, 0]))
    frame, sessions = C.simulate_world(rng, P["dgps"]["N1_GAUSS_CONST"], P["world"], 126, "2015-01")
    dates = sorted(frame["date"].unique())
    assert dates[0][:7] == "2015-01" and len(dates) == 141
    folds = E.folds(dates, sessions, 126)
    assert [y for y, _, _ in folds] == ["2021", "2022", "2023", "2024", "2025", "2026"]
    assert set(frame.loc[frame["cwStatus"].eq("NOT_MATURED"), "date"]) == {d for d in dates if d > "2026-02-27"}
    assert set(E.h1_columns("PROFIT")[1]) <= set(frame.columns)


def test_the_world_is_deterministic_per_stream_and_its_features_are_finite():
    P = protocol()
    dgp = P["dgps"]["N1_GAUSS_CONST"]
    a, _ = C.simulate_world(np.random.default_rng(np.random.SeedSequence([1, 2, 3])), dgp, P["world"], 126, "2015-01")
    b, _ = C.simulate_world(np.random.default_rng(np.random.SeedSequence([1, 2, 3])), dgp, P["world"], 126, "2015-01")
    assert a.equals(b)                                   # deterministic stream
    cols = ["REL_MOM_126", "DOWNSIDE_VOL_126", "MEDIAN_netIncomeToAssets"]
    assert np.isfinite(a[cols].to_numpy(float)).all()


def test_effect_kappa_is_zero_under_the_null_and_monotone_in_ic():
    assert C.effect_kappa(0, 126, 0.01, 0.95) == 0.0
    ks = [C.effect_kappa(ic, 126, 0.01, 0.95) for ic in (0.05, 0.1, 0.2)]
    assert ks == sorted(ks) and ks[0] > 0


def test_replicate_is_deterministic_and_summary_classifies():
    P = protocol()
    cell = C.cells(P)[0]
    r1, r2 = C.replicate(P, cell, 0, 11), C.replicate(P, cell, 0, 11)
    assert r1 == r2 and r1["testDates"] > 0
    s = C.summarise_cell(P, cell, [r1, r2])
    assert s["candidates"]["C0_REGISTERED_MBB"]["0.05"]["sizeDecision"] in ("PASS", "FAIL", "INCONCLUSIVE")
