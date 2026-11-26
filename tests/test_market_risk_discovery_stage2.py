"""Market Risk Discovery Stage 2: the frozen P1 design on synthetic worlds, its outcome-free structure on the real
sample, and the one-shot harness's refusals. No test joins a real credit value with a real label."""
from __future__ import annotations

import ast
import json
from pathlib import Path

import numpy as np
import pytest

from research.market_risk_discovery_v1 import baseline_census as B
from research.market_risk_discovery_v1 import panels as P
from research.market_risk_discovery_v1 import stage2_design as D
from research.market_risk_discovery_v1 import stage2_readiness as R
from research.market_risk_discovery_v1 import stage3_execute as X

HERE = Path(P.__file__).resolve().parent
STARTS = (40, 80, 130, 170, 215, 255)


def world(seed: int, effect: float, n: int = 300, flag_rate: float = 0.2):
    """Fully synthetic: a month-end every 21 sessions, six episodes, a persistent flag shifted up by `effect` in the
    126 sessions before each start, M1 features pure noise."""
    rng = np.random.default_rng(seed)
    idx = 21 * np.arange(n)
    dates = [f"{1990 + i // 12:04d}-{i % 12 + 1:02d}-28" for i in range(n)]
    starts = {f"EP{k}": 21 * s + 10 for k, s in enumerate(STARTS)}
    z = np.empty(n)
    z[0] = rng.normal()
    for t in range(1, n):
        z[t] = 0.8 * z[t - 1] + 0.6 * rng.normal()
    pre = np.array([any(0 < s - i <= D.HORIZON for s in starts.values()) for i in idx])
    z = z + effect * pre
    flags = (z > np.quantile(z, 1 - flag_rate)).astype(float)
    rows = []
    for i, t in enumerate(idx):
        hit = [e for e, s in starts.items() if t < s <= t + D.HORIZON]
        y = 1 if hit else (0 if t + D.HORIZON <= idx[-1] else None)
        rows.append(D.Row(int(t), dates[i], float(rng.normal()), float(rng.normal()), float(flags[i]), y,
                          hit[0] if hit else None))
    refits = D.refit_points([(d, int(t)) for d, t in zip(dates, idx)])
    return D.Panel(rows), refits, [(int(t), float(f)) for t, f in zip(idx, flags)], starts


def test_ridge_logit_recovers_direction():
    rng = np.random.default_rng(0)
    x = rng.normal(size=2000)
    y = (rng.random(2000) < 1 / (1 + np.exp(-(-1 + 1.5 * x)))).astype(float)
    b = D.ridge_logit(np.column_stack([np.ones(2000), x]), y)
    assert b[1] == pytest.approx(1.5, abs=0.2) and b[0] == pytest.approx(-1, abs=0.2)


def test_constant_flag_makes_m2_identical_to_m1():
    p, refits, seq, _ = world(1, 0.0)
    p.X[:, 2] = 0.0
    start = D.evaluation_start(p, refits)
    pr = D.walk_forward(p, refits, start)
    assert np.allclose(pr["M1"], pr["M2"])


def test_planted_effect_is_detected():
    p, refits, seq, starts = world(2, 3.0)
    res = D.primary(p, refits, seq)
    assert res["dBrier"] > 0 and res["rotationP"] <= 0.05


def test_rotation_null_is_not_systematically_rejecting():
    rejections = sum(D.primary(*world(100 + s, 0.0)[:3])["rotationP"] <= 0.05 for s in range(8))
    assert rejections <= 2


def test_walk_forward_never_reads_an_unmatured_label():
    p, refits, seq, _ = world(3, 1.0)
    start = D.evaluation_start(p, refits)
    base = D.walk_forward(p, refits, start)
    year = start + 5
    ev = D.evaluation_mask(p, start)
    poisoned = D.Panel(p.rows)
    poisoned.X = p.X.copy()
    unmatured = p.labelled & (p.idx + D.HORIZON > refits[year])
    poisoned.y = p.y.copy()
    poisoned.y[unmatured] = 1 - poisoned.y[unmatured]
    again = D.walk_forward(poisoned, refits, start)
    keep = p.year[ev] <= year
    for m in D.MODELS:
        assert np.allclose(base[m][keep], again[m][keep])


def test_early_resolved_positive_is_not_used_early():
    p, refits, _, _ = world(4, 0.0)
    year = 1996
    m = D.matured_mask(p, refits[year])
    assert np.all(p.idx[m] + D.HORIZON <= refits[year])
    late_pos = p.labelled & (p.y == 1) & (p.idx + D.HORIZON > refits[year]) & (p.idx < refits[year])
    assert not np.any(m & late_pos)


def test_rotation_is_a_permutation_that_keeps_the_evaluation_rows():
    p, refits, seq, _ = world(5, 0.0)
    pos, vals = D.sequence_positions(p, seq)
    shifts = D.rotation_shifts(len(vals))
    assert shifts[0] == D.ROTATION_GUARD and shifts[-1] == len(vals) - D.ROTATION_GUARD
    for k in (shifts[0], shifts[len(shifts) // 2]):
        r = D.rotated(pos, vals, k)
        assert sorted(r) == sorted(vals)
        trans = lambda v: int(np.sum(v[1:] != v[:-1]))  # noqa: E731
        assert abs(trans(r) - trans(vals)) <= 2


def test_block_bootstrap_is_deterministic_and_brackets_the_mean():
    d = np.random.default_rng(6).normal(0.01, 0.05, size=150)
    a, b = D.block_bootstrap_ci(d), D.block_bootstrap_ci(d)
    assert a == b and a["lo"] < a["mean"] < a["hi"]


def test_leave_one_episode_out_drops_each_positive_episode():
    d = np.array([1.0, 2.0, 3.0, 4.0])
    eps = np.array(["A", "A", "B", ""], dtype=object)
    y = np.array([1, 1, 1, 0], dtype=float)
    assert D.leave_one_episode_out(d, eps, y) == {"A": 3.5, "B": 7 / 3}


def test_purged_cv_never_trains_on_an_overlapping_window(monkeypatch):
    p, _, _, starts = world(7, 1.0)
    seen = []
    real = D.fit_predict

    def spy(Xtr, ytr, Xte, model):
        seen.append((Xtr.copy(), Xte.copy()))
        return real(Xtr, ytr, Xte, model)

    monkeypatch.setattr(D, "fit_predict", spy)
    D.purged_cv(p, starts)
    folds = D.episode_folds(p, starts)
    for f in sorted(set(folds[p.labelled])):
        te = p.labelled & (folds == f)
        lo, hi = p.idx[te].min(), p.idx[te].max()
        tr = p.labelled & (folds != f) & ((p.idx + D.HORIZON < lo) | (p.idx > hi + D.HORIZON))
        assert not np.any(tr & (p.idx >= lo) & (p.idx <= hi))


def test_verdict_truth_table():
    ok = {"A": 0.1, "B": 0.2}
    assert D.verdict(0.01, 0.01, ok) == "EXPLORATORY_INCREMENTAL_SUPPORT"
    assert D.verdict(0.01, 0.05, ok) == "EXPLORATORY_INCREMENTAL_SUPPORT"
    assert D.verdict(0.01, 0.20, ok) == "DIRECTIONAL_NOT_SEPARATED"
    assert D.verdict(0.01, 0.01, {"A": 0.1, "B": -0.1}) == "DIRECTIONAL_NOT_SEPARATED"
    assert D.verdict(-0.01, 0.01, ok) == "NOT_DETECTED_UNDERPOWERED"
    assert set(D.VERDICTS) >= {"DATA_INSUFFICIENT", "EXPLORATORY_INCREMENTAL_SUPPORT"}


def test_full_evaluate_runs_on_a_synthetic_world():
    p, refits, seq, starts = world(8, 2.0)
    out = D.evaluate(p, refits, seq, starts)
    assert out["verdict"] in D.VERDICTS
    assert set(out["primary"]["leaveOneEpisodeOut"]) == set(out["structure"]["evaluationEpisodes"])
    assert out["auxiliary"]["events"]["evaluationEpisodes"] == len(out["structure"]["evaluationEpisodes"])
    assert sum(out["auxiliary"]["eventHitNullDistribution"].values()) == out["structure"]["rotations"]


def test_real_structure_is_outcome_free_and_frozen():
    c = P.common_rows("presence")
    assert {r.flag for r in c["rows"]} == {0.0}
    g = D.structure_gate(D.Panel(c["rows"]), D.refit_points(c["monthEnds"]), c["flagSequence"])
    assert g["pass"] and g["start"] == 2001 and g["evaluationRows"] == 128 and g["evaluationPositives"] == 23
    assert g["evaluationEpisodes"] == ["2008-01-18", "2018-12-20", "2020-03-09", "2022-05-09", "2025-04-04"]
    assert g["trainingEpisodesAtStart"] == ["1998-08-31", "2000-12-20"] and g["rotations"] == 314


def test_credit_flag_is_stage1_rule_unchanged():
    seq = P.credit_side()
    assert seq[0][0] == "1998-03" and len(seq) == 337
    stage1 = B.candidate_credit_flags()["WIDEN_3M_ABOVE_EXPANDING_P80"]
    c = P.common_rows("presence")
    assert stage1["firstDefined"] == "1998-03"
    assert stage1["definedMonths"] == len(c["rows"])


def test_expanding_flag_reads_no_later_value():
    rng = np.random.default_rng(9)
    vals = list(rng.normal(size=80))
    f = lambda v, i: B._above_expanding(i, lambda j: v[j], 0.8, 12)  # noqa: E731
    later = vals[:50] + list(rng.normal(size=30) * 10)
    assert all(f(vals, i) == f(later, i) for i in range(50))


def test_stage1_binomial_was_anticonservative():
    o = json.loads((HERE / "evidence" / "stage2-readiness.json").read_text())["opportunityNull"]
    assert o["stage1BinomialCriticalHitsAt5pct"] == 3
    assert o["tailProbabilityOfStage1CriticalUnderOpportunityNull"] > 0.2
    assert R.poisson_binomial([0.5, 0.5]) == [0.25, 0.5, 0.25]


def test_only_the_stage3_harness_asks_for_real_flags():
    for path in HERE.glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "common_rows":
                arg = node.args[0].value if node.args and isinstance(node.args[0], ast.Constant) else None
                if arg == "real":
                    assert path.name in ("stage3_execute.py", "stage3_execute_v2.py"), path


def test_v1_protocol_hash_file_still_matches_its_json():
    """The v1 protocol is kept as the historical record of what was preregistered at 87c824c3."""
    import hashlib
    assert hashlib.sha256((HERE / "protocol-stage2.json").read_bytes()).hexdigest() == \
        (HERE / "protocol-stage2.sha256").read_text().split()[0]


def test_v1_harness_is_permanently_superseded(tmp_path, monkeypatch):
    """Independent audit A1/B1: the v1 harness refuses every call, with or without an authorization file."""
    for require in (True, False):
        with pytest.raises(X.ExecutionRefused, match="SUPERSEDED_BY_PROTOCOL_V2"):
            X.verify(require_authorization=require)
    with pytest.raises(X.ExecutionRefused, match="SUPERSEDED_BY_PROTOCOL_V2"):
        X.execute()


def test_no_result_or_marker_or_authorization_is_committed():
    assert not X.AUTHORIZATION.exists() and not X.MARKER.exists() and not X.RESULT.exists()
