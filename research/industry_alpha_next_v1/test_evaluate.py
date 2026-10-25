"""Evaluator invariants on invented data only."""
import numpy as np
import pandas as pd
import pytest

from pipeline import replay_calendar as RC
from research.industry_alpha_next_v1 import evaluate as E
from research.industry_alpha_next_v1 import run_study as R
from research.industry_alpha_next_v1 import study as S

SESSIONS = RC.sessions("2001-01-01", "2026-12-31", "KR")


def world(signal=0.0, months=260, start="2003-01-31", seed=3):
    rows, tg, _ = R.synthetic_world(seed=seed, months=months, signal=signal, start=start)
    return rows.merge(tg, on=["date", "industry"])


def test_folds_purge_every_training_label_before_the_embargo():
    dates = sorted(world(months=120)["date"].unique())
    for h in S.HORIZONS:
        for year, train, test in E.folds(dates, SESSIONS, h):
            start = E.signal_position(SESSIONS, test[0])
            assert all(E.label_exit_position(SESSIONS, d, h) < start - S.EMBARGO_SESSIONS for d in train)
            assert all(d[:4] == year for d in test) and max(train) < min(test)
            assert len(train) >= 12 * S.MIN_TRAINING_YEARS


def test_future_labels_cannot_move_a_forecast():
    f = world(months=140)
    cols = list(E.h1_columns("MOM")[1])
    base, _ = E.oof_predictions(f, cols, "cwRelative", SESSIONS, 126)
    poisoned = f.copy()
    late = poisoned["date"] >= "2012-01-01"
    poisoned.loc[late, "cwRelative"] = 1e6 * np.sign(np.random.default_rng(0).normal(size=late.sum()))
    pred, _ = E.oof_predictions(poisoned, cols, "cwRelative", SESSIONS, 126)
    keep = f["date"] < "2012-01-01"
    assert np.allclose(base[keep].dropna(), pred[keep].dropna())
    assert base[keep].notna().sum() > 0


def test_preprocessing_is_train_only():
    f = world(months=120)
    cols = ["REL_MOM_126", "HHI"]
    train, test = f[f.date < "2009-01-01"], f[f.date >= "2009-01-01"]
    A1, B1 = E.design(train, test, cols)
    test2 = test.copy()
    test2.iloc[0, test2.columns.get_loc("REL_MOM_126")] = 1e9
    A2, B2 = E.design(train, test2, cols)
    assert np.array_equal(A1, A2) and np.allclose(B1[1:], B2[1:])


def test_missing_values_are_imputed_with_an_indicator_never_zeroed_away():
    f = world(months=80)
    f.loc[f.index[::5], "REL_MOM_126"] = np.nan
    A_, B_ = E.design(f, f, ["REL_MOM_126"])
    assert A_.shape[1] == 2 and np.isfinite(A_).all()


def test_admission_is_paired_and_counts_every_unresolved_reason():
    f = world(months=40)
    f.loc[f.index[:3], "cwStatus"] = "UNRESOLVED_TERMINAL_OR_DISTRIBUTION_EVIDENCE"
    f.loc[f.index[:3], "cwRelative"] = np.nan
    one_date = f.date.unique()[5]
    f.loc[(f.date == one_date) & (f.industry.isin(["G0", "G1", "G2"])), "cwStatus"] = "UNRESOLVED_INCOMPLETE_COHORT_OR_WINDOW"
    pop, rep = E.admit(f, "cwRelative", "cwStatus")
    assert rep["unresolvedRowsByReason"] == {"UNRESOLVED_INCOMPLETE_COHORT_OR_WINDOW": 3,
                                            "UNRESOLVED_TERMINAL_OR_DISTRIBUTION_EVIDENCE": 3}
    assert rep["thinDates"] == 2 and one_date not in set(pop.date)
    assert rep["admittedRows"] == len(pop) and pop.cwStatus.eq("MATURED").all()


def test_a_planted_edge_is_found_and_a_null_world_stays_quiet():
    planted = E.contrast(world(signal=0.4), *E.h1_columns("MOM"), "cwRelative", "cwStatus", SESSIONS, 126)
    null = E.contrast(world(signal=0.0), *E.h1_columns("MOM"), "cwRelative", "cwStatus", SESSIONS, 126)
    assert planted["status"] == null["status"] == "EVALUATED"
    assert planted["p"] < 0.01 and planted["meanLossReduction"] > 0
    assert null["p"] > 0.05


def test_insufficient_support_enters_the_family_at_one():
    short = E.contrast(world(signal=0.4, months=150, start="2012-01-31"), *E.h1_columns("MOM"),
                       "cwRelative", "cwStatus", SESSIONS, 126)
    assert short["status"] == "INSUFFICIENT_SUPPORT" and short["p"] == 1.0
    assert 0 < short["descriptiveBootstrapP"] <= 1


def test_bootstrap_is_deterministic_and_never_zero():
    d = np.random.default_rng(1).normal(loc=5, size=60)
    p1, p2 = E.moving_block_bootstrap_p(d), E.moving_block_bootstrap_p(d)
    assert p1 == p2 == 1 / (S.BOOTSTRAP["draws"] + 1)


def test_holm_matches_the_step_down_definition():
    out = E.holm({"a": 0.001, "b": 0.03, "c": 0.04}, alpha=0.05)
    assert out["a"]["reject"] and out["b"]["reject"] is False and out["c"]["reject"] is False
    assert out["a"]["pHolm"] == pytest.approx(0.003) and out["b"]["pHolm"] == pytest.approx(0.06)
    assert out["c"]["pHolm"] == pytest.approx(0.06)
    assert E.holm({"a": 0.001, "b": 0.02, "c": 0.04})["c"]["reject"]


def test_family_has_36_slots_and_missing_slots_are_one():
    fam = E.family({"KR_H126_MOM": {"p": 0.0001}})
    assert len(fam) == 36 == len(S.slots())
    assert all(v["p"] == 1.0 for k, v in fam.items() if k != "KR_H126_MOM")


def test_sequential_gate_keeps_h2_closed_without_an_h1_pass():
    res = E.run_kr_horizon(world(signal=0.0), SESSIONS, 126, sequential_gate=True)
    assert res["KR_H126_LEADER_DIFFUSION"]["status"] == "GATED_CLOSED_NO_H1_PASS"
    opened = E.run_kr_horizon(world(signal=0.6), SESSIONS, 126, sequential_gate=True)
    assert opened["KR_H126_LEADER_DIFFUSION"]["status"] in ("EVALUATED", "INSUFFICIENT_SUPPORT")


def test_centring_removes_a_common_market_move():
    f = world(months=140)
    shifted = f.copy()
    shifted["cwRelative"] += shifted["date"].map({d: i * 10.0 for i, d in enumerate(sorted(f.date.unique()))})
    a = E.contrast(f, *E.h1_columns("MOM"), "cwRelative", "cwStatus", SESSIONS, 126)
    b = E.contrast(shifted, *E.h1_columns("MOM"), "cwRelative", "cwStatus", SESSIONS, 126)
    assert a["meanLossReduction"] == pytest.approx(b["meanLossReduction"], rel=1e-6, abs=1e-9)


def test_anticipation_split_reports_three_terciles():
    out = E.anticipation_split(world(months=160), "CASH", SESSIONS, 126)
    assert set(out) == {"0", "1", "2"} and all(v["testDates"] > 0 for v in out.values())


def test_date_weights_sum_to_one_per_date():
    w = E.date_weights(["a", "a", "b"])
    assert w.tolist() == [0.5, 0.5, 1.0]
    assert pd.Series(w).groupby(["a", "a", "b"]).sum().tolist() == [1.0, 1.0]
