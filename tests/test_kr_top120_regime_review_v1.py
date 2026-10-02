"""kr-top120-regime-review-v1: synthetic-only tests of the frozen protocol and harness.

EXPLORATORY_POST_OUTCOME_REGIME_DIAGNOSTIC. No historical outcome is read anywhere here. Every authorization / lifecycle test
builds its OWN synthetic repository, so no test depends on whether the real repository is pre- or post-seal.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import shutil

import numpy as np
import pandas as pd
import pytest

from pipeline import kr_factor_anatomy as A
from pipeline import kr_factor_anatomy_execution as AE
from pipeline import kr_market_risk_overlay as O
from pipeline import kr_model_portfolio_execution as X
from pipeline import kr_top120_regime_review as R
from pipeline import kr_top120_regime_review_execution as E
from pipeline import kr_value_quality_catalyst as F
from pipeline import replay_calendar as RC

ROOT = Path(__file__).resolve().parents[1]
SAMSUNG, HYNIX, KEPCO, SEMCO = "005930.KS", "000660.KS", "015760.KS", "009150.KS"
PRED = "docs/results/kr-factor-anatomy-v1-"


def spec():
    return json.loads((ROOT / E.SPEC_PATH).read_text())


def small_spec():
    """A COPY with smaller label minimums so a short synthetic panel can be measured. The sealed spec is never edited."""
    s = spec()
    s["labelRules"] = {**s["labelRules"], "sliceMinimumDates": 8, "minimumDatesFull": 20}
    return s


# --------------------------------------------------------------------------- #
# Synthetic panel in the anatomy's shape
# --------------------------------------------------------------------------- #
def make_panel(n_dates=130, n_names=62, seed=0, nan_rate=0.05, start="2023-06-02"):
    rng = np.random.default_rng(seed)
    dates = [str(d.date()) for d in pd.date_range(start, periods=n_dates, freq="7D")]
    tickers = [f"{i:06d}.KS" for i in range(1, n_names + 1)] + [SAMSUNG, HYNIX, KEPCO, SEMCO]
    rows = []
    for i, d in enumerate(dates):
        trend, vol = bool(i % 2), bool((i // 7) % 2)
        risk = None if i < 3 else (1.0, .7, .4)[int(trend) + int(vol)]
        for t in tickers:
            row = {"date": d, "ticker": t}
            for name in R.FACTORS:
                row[name] = float(rng.normal()) if rng.random() > nan_rate else np.nan
            row["marketCap"] = float(np.exp(rng.normal(25, 1))) * (1e4 if t == SAMSUNG else 3e3 if t == HYNIX else 1.0)
            row["trendAdverse"], row["volAdverse"], row["riskMultiplier"] = (None, None, None) if risk is None else (trend, vol, risk)
            row["netIncomeImprovementToAssets"] = float(rng.normal()) if rng.random() > .3 else np.nan
            for h in (126, 252):
                s = str(h)
                ok = rng.random() > .05
                row["entry" + s] = str((pd.Timestamp(d) + pd.Timedelta(days=3)).date())
                row["exit" + s] = str((pd.Timestamp(d) + pd.Timedelta(days=int(h * 1.4))).date())
                row["stock" + s], row["bench" + s] = float(rng.normal(.05, .2)), float(rng.normal(.03, .1))
                row["rawStatus" + s] = "MATURED" if ok else "MISSING_FORWARD_PRICE_OR_DELISTING"
                row["status" + s] = row["rawStatus" + s]
            rows.append(row)
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def analysis():
    s = small_spec()
    panel = R.add_outcomes(make_panel(), s["benchmarks"]["minimumPeers"])
    return {"spec": s, "panel": panel, "out": R.analyze_all(panel, s)}


# --------------------------------------------------------------------------- #
# Frozen identity
# --------------------------------------------------------------------------- #
def test_spec_identity_status_limitation_and_predecessor_pins():
    s, sha = E.load_spec()
    assert s["studyId"] == "kr-top120-regime-review-v1" and s["scientificStatus"] == "EXPLORATORY_POST_OUTCOME_REGIME_DIAGNOSTIC"
    assert E.digest(s) == sha == (ROOT / "research_specs/kr-top120-regime-review-v1.sha256").read_text().strip()
    for phrase in ("cannot confirm a factor", "validate a strategy", "rescue kr-model-overlay-portfolio-v1", "production weights",
                   "best factor", "tune a threshold", "independent replication"):
        assert phrase in s["limitation"]
    p = s["predecessor"]
    assert p["sha256"] == {"result": "8518ec8cae95d0a23e964aab147e20659f17437fcd6fec6cb7f64cfa2b98a9e7",
                           "report": "2ffbb3458660c74fcbacd148cb2b8d7c7013ac7967978a6c8334b6af7b9f892e",
                           "manifest": "3f8cdd9e5cf82b58f8526078c545b9ce8e116b3bf196e474e807a22a4cd59df9",
                           "provenance": p["sha256"]["provenance"]}
    assert p["artifactArchiveSha256"] == "f8020bdac9878f523091881d129e3c414234012c17e1fd61e1e49b6d6538b80f"
    assert p["specSha256"] == "ceb97f481ae7261e89da4467fba03465f0c78cc3654cd799c26e5088ee3bc3d2"
    assert p["rawInputIdentitySha256"] == "233df37ed205cc6b48828121e711417ccf961301dc58aa252430b343db9666a7"
    assert p["scientificStatus"] == "EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY"
    for key, rel in p["files"].items():
        assert hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == p["sha256"][key]


def test_sealed_anatomy_is_untouched_and_still_loads_under_its_own_identity():
    anatomy_spec, sha = AE.load_spec()                      # raises if any sealed anatomy dependency byte moved
    assert sha == "ceb97f481ae7261e89da4467fba03465f0c78cc3654cd799c26e5088ee3bc3d2"
    mine = spec()["dependencyHashes"]
    for rel, wanted in anatomy_spec["dependencyHashes"].items():
        if rel in mine:
            assert mine[rel] == wanted                      # one byte, two pins
    assert E.verify_predecessor(spec())


def test_inherited_values_are_copies_of_the_anatomy_spec():
    s, a = spec(), json.loads((ROOT / "research_specs/kr-factor-anatomy-v1.json").read_text())
    for key in ("input", "statistics", "horizons", "benchmark", "developmentCutoff", "calendar"):
        assert s[key] == a[key]
    assert s["benchmarks"]["minimumPeers"] == s["statistics"]["decileMinimumNames"] == 50
    assert s["labelRules"]["minimumDatesFull"] == a["interpretation"]["minimumDatesForLabel"]
    assert s["labelRules"]["weakeningFraction"] == a["interpretation"]["monotonicityFloor"] == 0.5
    assert s["universe"]["scopeStatement"] == a["universes"]["scopeStatement"] and "TOP-120" in s["universe"]["scopeStatement"]


def test_exactly_the_eleven_anatomy_factors_in_frozen_order():
    expected = ["bookToMarketProxy", "earningsYieldProxy", "ocfYieldProxy", "netIncomeToAssets", "ocfToAssets",
                "negativeAccrualsToAssets", "relative126", "momentum121", "ocfImprovementToAssets", "negativeDownsideVol126", "logAdv60"]
    assert list(R.FACTORS) == expected == [f["name"] for f in spec()["factors"]] == list(F.RAW_FEATURES)
    bad = deepcopy(spec())
    bad["factors"].append({"name": "valueUpPolicyFactor", "family": "NEW"})
    with pytest.raises(ValueError, match="FACTOR_LIST_DIFFERS_FROM_ANATOMY"):
        R.analyze_all(pd.DataFrame(), bad)
    reordered = deepcopy(spec())
    reordered["factors"].reverse()
    with pytest.raises(ValueError, match="FACTOR_LIST_DIFFERS_FROM_ANATOMY"):
        R.analyze_all(pd.DataFrame(), reordered)


def test_registered_constants_equal_the_frozen_spec():
    s = spec()
    assert list(R.SLICES) == s["windowSlices"]["order"] and set(R.SLICES) == set(s["windowSlices"]["slices"]) and list(R.REGIME_STATES) == s["marketRegimes"]["states"]
    assert list(R.UNIVERSES) == s["megaCapSensitivities"]["universes"] and list(R.LABELS) == s["labelRules"]["labels"]
    assert {k: list(v) for k, v in R.FIXED_EXCLUSIONS.items() if v} == s["megaCapSensitivities"]["fixedIdentities"]
    assert list(R.OUTCOMES) == list(s["benchmarks"]["variants"]) and tuple(R.HORIZONS) == tuple(s["horizons"])
    assert R.RETURN_BASIS == s["returnBasis"]["label"] == A.RETURN_BASIS
    assert not set(s["labelRules"]["forbiddenLabels"]) & set(R.LABELS)


# --------------------------------------------------------------------------- #
# Chronology by outcome window
# --------------------------------------------------------------------------- #
CUT = "2026-09-14"


def membership(entry, exit_):
    return {n: bool(R.slice_mask(n, [entry], [exit_], CUT).iloc[0]) for n in R.SLICES}


def test_a_late_2024_signal_maturing_in_2025_is_a_recent_observation():
    m = membership("2024-12-30", "2025-07-01")                 # signal year 2024, outcome window inside 2025
    assert m["TOUCHES_2025_OR_LATER"] and not m["PRE_2025_COMPLETE_WINDOW"]
    assert not m["EXCLUDE_WINDOWS_TOUCHING_2025"] and not m["EXCLUDE_WINDOWS_TOUCHING_2025_OR_2026"]
    assert m["PRE_2026_COMPLETE_WINDOW"] and m["EXCLUDE_WINDOWS_TOUCHING_2026"] and not m["TOUCHES_2026"]
    assert m["FULL_SAMPLE"]


def test_windows_are_classified_mechanically_by_entry_and_exit():
    pre = membership("2024-01-02", "2024-07-01")
    assert pre["PRE_2025_COMPLETE_WINDOW"] and not pre["TOUCHES_2025_OR_LATER"] and pre["EXCLUDE_WINDOWS_TOUCHING_2025_OR_2026"]
    h252 = membership("2025-03-03", "2026-03-02")               # a 2025 H252 signal maturing inside 2026
    assert h252["TOUCHES_2026"] and not h252["PRE_2026_COMPLETE_WINDOW"] and not h252["EXCLUDE_WINDOWS_TOUCHING_2026"]
    assert not h252["EXCLUDE_WINDOWS_TOUCHING_2025_OR_2026"]
    spanning = membership("2024-06-03", "2026-02-02")           # spans all of 2025
    assert not spanning["EXCLUDE_WINDOWS_TOUCHING_2025"] and not spanning["EXCLUDE_WINDOWS_TOUCHING_2026"]
    only_2026 = membership("2026-01-02", "2026-07-01")
    assert only_2026["EXCLUDE_WINDOWS_TOUCHING_2025"] and not only_2026["EXCLUDE_WINDOWS_TOUCHING_2026"]
    assert not only_2026["EXCLUDE_WINDOWS_TOUCHING_2025_OR_2026"]
    after_cutoff = membership("2026-10-01", "2027-04-01")
    assert not after_cutoff["TOUCHES_2026"]                      # entry after the development cutoff
    edge_in, edge_out = membership("2024-12-31", "2025-01-01"), membership("2024-12-30", "2024-12-31")
    assert edge_in["TOUCHES_2025_OR_LATER"] and not edge_in["PRE_2025_COMPLETE_WINDOW"]
    assert edge_out["PRE_2025_COMPLETE_WINDOW"] and edge_out["EXCLUDE_WINDOWS_TOUCHING_2025"]


def test_an_observation_without_a_window_belongs_to_no_slice():
    for name in R.SLICES:
        assert not R.slice_mask(name, [None, "2024-01-01"], ["2024-06-01", None], CUT).any()
    with pytest.raises(ValueError, match="UNREGISTERED_SLICE"):
        R.slice_mask("SIGNAL_YEAR_2025", ["2025-01-01"], ["2025-06-01"], CUT)


def test_a_slice_removes_outcomes_not_ranks(analysis):
    panel = analysis["panel"]
    ranked = A.add_signal_time_ranks(panel, list(R.FACTORS))
    inside = R.slice_mask("PRE_2025_COMPLETE_WINDOW", ranked.entry126, ranked.exit126, CUT).to_numpy()
    assert inside.any() and not inside.all()
    view_full = R.factor_view(ranked, "bookToMarketProxy", ranked.abs126.to_numpy(), analysis["spec"])
    view_slice = R.factor_view(ranked, "bookToMarketProxy", np.where(inside, ranked.abs126, np.nan), analysis["spec"])
    assert view_slice["datesWithDeciles"] < view_full["datesWithDeciles"]
    assert ranked["bookToMarketProxy__pct"].notna().sum() > 0         # ranks untouched by any slice


def test_h252_slice_without_enough_dates_is_data_insufficient(analysis):
    out = analysis["out"]["result"]["factors"][0]["horizons"]
    h252_2026 = out["252"]["slices"]["TOUCHES_2026"]
    assert h252_2026["status"] == "DATA_INSUFFICIENT" or h252_2026["datesWithDeciles"] >= analysis["spec"]["labelRules"]["sliceMinimumDates"]
    strict = deepcopy(analysis["spec"])
    strict["labelRules"]["sliceMinimumDates"] = 10_000
    ranked = A.add_signal_time_ranks(analysis["panel"], ["bookToMarketProxy"])
    assert R.factor_view(ranked, "bookToMarketProxy", ranked.abs252.to_numpy(), strict)["status"] == "DATA_INSUFFICIENT"


# --------------------------------------------------------------------------- #
# Signal-time market states
# --------------------------------------------------------------------------- #
def test_signal_time_state_uses_no_future_price():
    days = RC.sessions("2013-01-01", "2016-12-30", "KR")
    rng = np.random.default_rng(3)
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, .01, len(days)))), index=days)
    date = str(days[400].date())
    base = O.state_at(pd.DataFrame({"Close": close}), date)
    future = close.copy()
    future.iloc[401:] = future.iloc[401:] * np.exp(rng.normal(0, 2, len(days) - 401))      # violent future shock
    assert O.state_at(pd.DataFrame({"Close": future}), date) == base
    assert base["status"] == "READY" and set(("trendAdverse", "volAdverse", "riskMultiplier")) <= set(base)
    assert base["riskMultiplier"] == (1.0, .7, .4)[int(base["trendAdverse"]) + int(base["volAdverse"])]


def test_the_signal_time_panel_carries_no_outcome_column():
    import inspect
    source = inspect.getsource(E.signal_time_panel)
    for banned in ("endpoint_returns", "target_from_sessions", "stock126", "exit126", "status126"):
        assert banned not in source


def test_state_masks_partition_rows_and_leave_unreadable_states_out(analysis):
    frame = analysis["panel"]
    masks = R.state_masks(frame)
    assert set(masks) == set(R.REGIME_STATES)
    for a, b in (("TREND_OK", "TREND_BAD"), ("VOL_OK", "VOL_HIGH")):
        assert not (masks[a] & masks[b]).any()
        assert (masks[a] | masks[b]).sum() == frame.riskMultiplier.notna().sum()
    joint = sum(masks[k].astype(int) for k in ("TREND_OK_VOL_OK", "TREND_BAD_VOL_OK", "TREND_OK_VOL_HIGH", "TREND_BAD_VOL_HIGH"))
    assert joint.max() == 1 and joint.sum() == frame.riskMultiplier.notna().sum()
    assert sum(masks[f"RISK_MULTIPLIER_{m}"].sum() for m in (1.0, 0.7, 0.4)) == frame.riskMultiplier.notna().sum()
    assert not masks["TREND_OK"][frame.riskMultiplier.isna()].any()


# --------------------------------------------------------------------------- #
# Mega-cap sensitivities
# --------------------------------------------------------------------------- #
def test_samsung_and_hynix_exclusions_are_exact_fixed_and_immutable():
    assert R.FIXED_EXCLUSIONS["EXCLUDE_SAMSUNG_ELECTRONICS"] == (SAMSUNG,)
    assert R.FIXED_EXCLUSIONS["EXCLUDE_SK_HYNIX"] == (HYNIX,)
    assert R.FIXED_EXCLUSIONS["EXCLUDE_BOTH"] == (SAMSUNG, HYNIX)
    assert all(isinstance(v, tuple) for v in R.FIXED_EXCLUSIONS.values())
    panel = make_panel(n_dates=4)
    for name, names in R.FIXED_EXCLUSIONS.items():
        reduced, removed = R.apply_universe(panel, name)
        assert set(removed.ticker) == set(names) and not reduced.ticker.isin(names).any()
        assert len(reduced) + len(removed) == len(panel)
    with pytest.raises(ValueError, match="UNREGISTERED_SENSITIVITY_UNIVERSE"):
        R.apply_universe(panel, "EXCLUDE_KEPCO")


def test_no_hand_picked_third_company_can_enter_the_exclusion_set():
    panel = make_panel(n_dates=6)
    allowed = {SAMSUNG, HYNIX}
    for name in ("EXCLUDE_SAMSUNG_ELECTRONICS", "EXCLUDE_SK_HYNIX", "EXCLUDE_BOTH"):
        _, removed = R.apply_universe(panel, name)
        assert set(removed.ticker) <= allowed
    _, removed = R.apply_universe(panel, "EXCLUDE_DYNAMIC_TOP2_MARKET_CAP")
    assert {KEPCO, SEMCO}.isdisjoint(removed.ticker)                # present, large winners, never removed by hand
    assert removed.groupby("date").size().max() == 2
    assert R.FIXED_EXCLUSIONS["FULL_TOP120"] == ()


def test_dynamic_top2_uses_only_signal_date_market_cap():
    panel = make_panel(n_dates=5)
    expected = {d: list(g.sort_values(["marketCap", "ticker"], ascending=[False, True]).ticker.head(2)) for d, g in panel.groupby("date")}
    assert R.dynamic_top_names(panel) == expected
    changed = panel.copy()
    for col in changed.columns:
        if col.startswith(("stock", "bench", "entry", "exit", "status", "rawStatus")):
            changed[col] = changed[col].sample(frac=1, random_state=1).to_numpy()          # scramble every outcome column
    assert R.dynamic_top_names(changed) == expected
    tie = pd.DataFrame({"date": ["d"] * 4, "ticker": ["B", "A", "C", "D"], "marketCap": [5.0, 5.0, 5.0, np.nan]})
    assert R.dynamic_top_names(tie) == {"d": ["A", "B"]}                                    # tie by ticker; NaN never removed
    _, removed = R.apply_universe(panel.assign(marketCap=panel.marketCap.where(panel.ticker != SAMSUNG)), "EXCLUDE_DYNAMIC_TOP2_MARKET_CAP")
    assert SAMSUNG not in set(removed.ticker)


def test_same_date_ranks_are_recomputed_after_an_exclusion():
    panel = make_panel(n_dates=3)
    full = A.add_signal_time_ranks(panel, ["bookToMarketProxy"])
    reduced, removed = R.ranked_universe(panel, "EXCLUDE_BOTH", ["bookToMarketProxy"])
    assert len(removed) == 6 and len(reduced) == len(panel) - 6
    for date, group in reduced.groupby("date"):
        expected = A.pct_rank(group["bookToMarketProxy"].to_numpy())
        np.testing.assert_array_equal(group["bookToMarketProxy__pct"].to_numpy(), expected)
        assert group["bookToMarketProxy__n"].iloc[0] == int(group["bookToMarketProxy"].notna().sum())
    merged = full.merge(reduced, on=["date", "ticker"], suffixes=("_full", "_reduced"))
    assert not np.allclose(merged["bookToMarketProxy__pct_full"], merged["bookToMarketProxy__pct_reduced"], equal_nan=True)


def test_concentration_context_shares(analysis):
    rows = analysis["out"]["tables"]["concentration-context"]
    assert len(rows) == len(analysis["panel"].date.unique())
    first = rows[0]
    g = analysis["panel"][analysis["panel"].date == first["date"]]
    total = g.marketCap.sum()
    assert first["samsungElectronicsShare"] == pytest.approx(g.set_index("ticker").marketCap[SAMSUNG] / total)
    assert first["combinedShare"] == pytest.approx(first["samsungElectronicsShare"] + first["skHynixShare"])
    top = g.marketCap.sort_values(ascending=False)
    assert first["dynamicLargestShare"] == pytest.approx(top.iloc[0] / total) and first["dynamicTop2Share"] == pytest.approx(top.iloc[:2].sum() / total)
    assert rows[0]["riskMultiplier"] is None and rows[-1]["riskMultiplier"] is not None


# --------------------------------------------------------------------------- #
# Three distinct returns and the leave-one-out benchmark
# --------------------------------------------------------------------------- #
def one_date(values, date="2024-01-05"):
    return pd.DataFrame({"date": date, "ticker": [f"{i:06d}.KS" for i in range(len(values))]}), np.asarray(values, float)


def test_absolute_kodex_and_leave_one_out_returns_are_three_distinct_series():
    panel = make_panel(n_dates=2)
    out = R.add_outcomes(panel, 50)
    matured = panel.status126.eq("MATURED").to_numpy()
    np.testing.assert_allclose(out.abs126[matured], panel.stock126[matured])
    np.testing.assert_allclose(out.kodex126[matured], (panel.stock126 - panel.bench126)[matured])
    assert out.abs126[~matured].isna().all() and out.kodex126[~matured].isna().all() and out.loo126[~matured].isna().all()
    assert not np.allclose(out.abs126[matured], out.kodex126[matured])
    assert not np.allclose(out.kodex126[matured], out.loo126[matured], equal_nan=True)
    assert not np.allclose(out.abs126[matured], out.loo126[matured], equal_nan=True)


def test_leave_one_out_benchmark_excludes_the_subject_stock():
    rng = np.random.default_rng(5)
    r = rng.normal(.05, .2, 60)
    frame, _ = one_date(r)
    loo = R.leave_one_out_relative(r, frame.date, 50)
    for i in (0, 17, 59):
        others = np.delete(r, i)
        assert loo[i] == pytest.approx(r[i] - others.mean())
    bumped = r.copy()
    bumped[3] += 1.0                                                  # the subject's own return cannot move its benchmark
    shifted = R.leave_one_out_relative(bumped, frame.date, 50)
    assert shifted[3] - loo[3] == pytest.approx(1.0)
    assert shifted[4] - loo[4] == pytest.approx(-1.0 / 59)             # but it moves every OTHER stock's benchmark


def test_minimum_peer_count_is_enforced():
    frame, r = one_date(np.linspace(-.2, .3, 50))
    assert np.isnan(R.leave_one_out_relative(r, frame.date, 50)).all()                  # 49 peers < 50
    frame, r = one_date(np.linspace(-.2, .3, 51))
    assert np.isfinite(R.leave_one_out_relative(r, frame.date, 50)).all()              # exactly 50 peers
    r2 = r.copy()
    r2[:2] = np.nan
    out = R.leave_one_out_relative(r2, frame.date, 50)
    assert np.isnan(out).all()                                                         # valid names fell to 49: 48 peers


def test_missing_peers_are_never_zero_filled_and_order_does_not_matter():
    rng = np.random.default_rng(6)
    r = rng.normal(.05, .2, 70)
    r[:8] = np.nan
    frame, _ = one_date(r)
    out = R.leave_one_out_relative(r, frame.date, 50)
    assert np.isnan(out[:8]).all()                                      # an unresolved stock gets no benchmark value
    valid = np.flatnonzero(np.isfinite(r))
    i = valid[0]
    assert out[i] == pytest.approx(r[i] - np.mean(r[valid[1:]]))        # peers = the finite others only
    assert out[i] != pytest.approx(r[i] - np.nansum(np.delete(r, i)) / 69)   # not the zero-filled mean
    perm = rng.permutation(len(r))
    shuffled = R.leave_one_out_relative(r[perm], frame.date.to_numpy()[perm], 50)
    np.testing.assert_array_equal(shuffled, out[perm])


# --------------------------------------------------------------------------- #
# Mean, median and rank correlation are separate, and nothing is winsorised
# --------------------------------------------------------------------------- #
def planted_view(outlier=1e6, n_dates=40, n=60):
    """Factor rank is the stock's index. D10 mean is dominated by ONE huge winner while the D10 median and the rank
    correlation point the other way."""
    rows = []
    for d in range(n_dates):
        date = str((pd.Timestamp("2020-01-03") + pd.Timedelta(days=7 * d)).date())
        for j in range(n):
            y = -0.01 * (j / n)                                      # monotone DOWN in the factor
            if j == n - 1:
                y = outlier                                          # the single top-decile winner
            rows.append({"date": date, "ticker": f"{j:06d}", "f": float(j), "y": y})
    return pd.DataFrame(rows)


def test_mean_median_and_spearman_are_separate_outputs_and_no_winsorisation():
    s = small_spec()
    frame = A.add_signal_time_ranks(planted_view(), ["f"])
    view = R.factor_view(frame, "f", frame.y.to_numpy(), s)
    assert view["d10MinusD1"] > 1_000 and view["medianD10MinusD1"] < 0 and view["meanRankCorrelation"] < 0
    mild = A.add_signal_time_ranks(planted_view(outlier=0.5), ["f"])
    assert R.factor_view(mild, "f", mild.y.to_numpy(), s)["d10MinusD1"] < view["d10MinusD1"] / 1_000    # nothing was clipped
    one = frame[frame.date == frame.date.iloc[0]]
    d10 = one[one.f__pct >= .9].y
    assert view["d10MinusD1"] == pytest.approx(d10.mean() - one[one.f__pct < .1].y.mean())
    assert not any("winsor" in k.lower() for k in spec()["robustness"]) or spec()["robustness"]["noWinsorisation"] is True
    assert spec()["robustness"]["noWinsorisation"] and spec()["robustness"]["noTrimming"]


def view_stub(mean, median, rho, dates=200, status="MEASURABLE"):
    return {"datesWithDeciles": dates, "datesWithRankCorrelation": dates, "outcomeObservations": 1, "d10MinusD1": mean,
            "medianD10MinusD1": median, "meanRankCorrelation": rho, "annualD10MinusD1": {}, "spreadYearStability": {},
            "leaveBestYearOut": None, "status": status}


def label_views(full=(1, 1, 1), pre=(1, 1, 1), ex=None, recent=(1, 1, 1), both=(1, 1, 1), top2=(1, 1, 1),
                trend=((1, 1, 1), (1, 1, 1)), vol=((1, 1, 1), (1, 1, 1))):
    def v(t):
        return view_stub(*t) if t is not None else view_stub(math.nan, math.nan, math.nan, 0, "DATA_INSUFFICIENT")
    return {"FULL_SAMPLE": {"FULL_TOP120": v(full)},
            "SLICES": {"PRE_2025_COMPLETE_WINDOW": v(pre), "EXCLUDE_WINDOWS_TOUCHING_2025_OR_2026": v(pre if ex is None else ex),
                       "TOUCHES_2025_OR_LATER": v(recent)},
            "UNIVERSES": {"EXCLUDE_BOTH": v(both), "EXCLUDE_DYNAMIC_TOP2_MARKET_CAP": v(top2)},
            "REGIMES": {"TREND_OK": v(trend[0]), "TREND_BAD": v(trend[1]), "VOL_OK": v(vol[0]), "VOL_HIGH": v(vol[1])}}


def test_descriptive_labels_are_deterministic_and_follow_the_frozen_rules():
    c = spec()["labelRules"]
    label = lambda **kw: R.descriptive_label(label_views(**kw), c)                   # noqa: E731
    assert label() == "PERSISTENT_ACROSS_PRE_RECENT_AND_RECENT"
    assert label() == label()
    assert label(full=(None, 1, 1)) == "DATA_INSUFFICIENT" and label(full=(math.nan, 1, 1)) == "DATA_INSUFFICIENT"
    assert label(full=(0.0, 1, 1)) == "NO_CLEAR_PATTERN"
    assert label(full=(1, -1, -1)) == "OUTLIER_SENSITIVE"                           # mean +, both robust views not
    assert label(full=(1, -1, 1)) != "OUTLIER_SENSITIVE"                           # one robust view still agrees
    assert label(both=(-1, -1, -1)) == "MEGA_CAP_SENSITIVE" and label(top2=(.4, 1, 1)) == "MEGA_CAP_SENSITIVE"   # sign flip / < 0.5x
    assert label(top2=(.5, 1, 1)) == "PERSISTENT_ACROSS_PRE_RECENT_AND_RECENT"       # exactly 0.5x is not weaker
    assert label(pre=(-1, -1, -1), recent=(1, 1, 1)) == "RECENT_REGIME_CONCENTRATED"
    assert label(pre=(1, 1, 1), recent=(-1, -1, -1)) == "PRE_RECENT_ONLY"
    assert label(pre=(1, 1, 1), ex=(-1, -1, -1), recent=(1, 1, 1)) == "NO_CLEAR_PATTERN"      # views disagree: neither concentrated nor persistent
    assert label(pre=None, ex=None) == "DATA_INSUFFICIENT" and label(recent=None) == "DATA_INSUFFICIENT"
    assert label(trend=((1, 1, 1), (-1, -1, -1))) == "REGIME_DEPENDENT" and label(vol=((-1, 1, 1), (1, 1, 1))) == "REGIME_DEPENDENT"
    assert label(trend=((1, 1, 1), None)) == "PERSISTENT_ACROSS_PRE_RECENT_AND_RECENT"
    allowed = set(R.LABELS)
    for kw in ({}, {"full": (0.0, 1, 1)}, {"pre": (-1, -1, -1)}, {"recent": (-1, -1, -1)}, {"both": (-1, -1, -1)}):
        assert label(**kw) in allowed


def test_a_slice_shows_a_direction_only_when_mean_and_rank_correlation_agree():
    assert R.shows_direction(view_stub(1, -1, 1), 1) and not R.shows_direction(view_stub(1, 1, -1), 1)
    assert not R.shows_direction(view_stub(1, 1, 1, status="DATA_INSUFFICIENT"), 1) and not R.shows_direction(None, 1)


# --------------------------------------------------------------------------- #
# Fundamentals improved: three definitions never collapsed
# --------------------------------------------------------------------------- #
def test_the_three_success_definitions_are_distinct_and_keep_their_own_populations():
    n = 80
    rng = np.random.default_rng(8)
    frame = pd.DataFrame({"date": ["2024-01-05"] * n, "ticker": [f"{i:06d}.KS" for i in range(n)],
                          "flag": np.where(np.arange(n) < 40, 1.0, -1.0)})
    stock = rng.normal(.05, .2, n)
    stock[:6] = -.3                                              # improved companies that fell in absolute terms
    bench = np.full(n, .6)                                       # an unusually strong benchmark: most lag it
    frame["abs126"], frame["kodex126"] = stock, stock - bench
    frame["loo126"] = R.leave_one_out_relative(stock, frame.date, 50)
    frame.loc[:3, "loo126"] = np.nan                             # four improved names have no peer benchmark
    r = R.improvement_outcomes(frame, "flag", 126, np.ones(n, bool), spec())["IMPROVED"]
    assert set(r) == set(R.SUCCESS_DEFINITIONS)
    assert r["ABSOLUTE_UP"]["rate"] != r["BEATS_KODEX200"]["rate"] != r["BEATS_TOP120_EQUAL_WEIGHT"]["rate"]
    assert r["ABSOLUTE_UP"]["rate"] > r["BEATS_KODEX200"]["rate"]                      # rose, but lagged the strong benchmark
    assert r["ABSOLUTE_UP"]["observations"] == 40 and r["BEATS_TOP120_EQUAL_WEIGHT"]["observations"] == 36   # missing peer: out of denominator
    assert r["ABSOLUTE_UP"]["rate"] == pytest.approx((stock[:40] > 0).mean())
    assert r["BEATS_KODEX200"]["rate"] == pytest.approx(((stock - bench)[:40] > 0).mean())
    none = R.improvement_outcomes(frame, "flag", 126, np.zeros(n, bool), spec())["IMPROVED"]
    assert none["ABSOLUTE_UP"]["rate"] is None


# --------------------------------------------------------------------------- #
# Whole-grid assembly
# --------------------------------------------------------------------------- #
def test_the_whole_grid_keeps_all_factors_in_frozen_order_and_all_slices_and_states(analysis):
    result = analysis["out"]["result"]
    assert [f["factor"] for f in result["factors"]] == list(R.FACTORS)
    for f in result["factors"]:
        assert set(f["horizons"]) == {"126", "252"}
        for block in f["horizons"].values():
            assert set(block["slices"]) == set(R.SLICES) and set(block["universes"]) == set(R.UNIVERSES)
            assert set(block["regimes"]) == set(R.REGIME_STATES) and block["descriptiveLabel"] in R.LABELS
    tables = analysis["out"]["tables"]
    assert len(tables["executive-map"]) == 11 * 2 * len(R.SLICES) and len(tables["mega-cap-sensitivity"]) == 11 * 2 * 5
    assert [r["factor"] for r in tables["executive-map"][::16]] == [f for f in R.FACTORS for _ in range(2 * len(R.SLICES) // 16)]
    for row in tables["executive-map"][:8]:
        assert {"meanD10MinusD1", "medianD10MinusD1", "meanRankCorrelation"} <= set(row)
    assert {r["successDefinition"] for r in tables["fundamentals-improved"]} == set(R.SUCCESS_DEFINITIONS)
    assert {r["flag"] for r in tables["fundamentals-improved"]} == {"ocfImprovementUp", "netIncomeImprovementUp"}
    assert result["returnBasis"] == A.RETURN_BASIS and "limitation" in result and "cannot confirm a factor" in result["limitation"]


def test_no_pass_fail_promotion_best_factor_or_validated_semantics_anywhere(analysis):
    result = analysis["out"]["result"]
    assert R.assert_no_forbidden_keys(result)
    text = json.dumps(E.AE.json_safe(result)) + R.render_report(result, analysis["spec"])
    for banned in ('"PASS"', '"FAIL"', "BEST_FACTOR", "PRODUCTION_READY", "promotionEligible", "bestFactor", "recommendedPortfolio",
                   "factorWeight", "VALIDATED", "PROVEN"):
        assert banned not in text
    for bad in ({"validated": True}, {"a": {"bestFactor": "x"}}, {"x": [{"promotionEligible": True}]}, {"productionWeights": 1}):
        with pytest.raises(ValueError, match="FORBIDDEN_OUTPUT_KEY"):
            R.assert_no_forbidden_keys(bad)
    assert "cannot confirm a factor" in R.render_report(result, analysis["spec"])


def test_analysis_and_outputs_are_deterministic(analysis, tmp_path):
    again = R.analyze_all(analysis["panel"].sample(frac=1, random_state=4).reset_index(drop=True), analysis["spec"])
    assert E.AE.json_safe(again["result"]["factors"]) == E.AE.json_safe(analysis["out"]["result"]["factors"])
    identity, s, counters = {"sha256": "a" * 64}, analysis["spec"], E.Counters()
    manifests = [E.write_outputs(tmp_path / n, analysis["out"], R.render_report(analysis["out"]["result"], s), s, "f" * 64, identity, counters)
                 for n in ("one", "two")]
    assert manifests[0] == manifests[1]
    for rel in manifests[0]["files"]:
        assert (tmp_path / "one" / rel).read_bytes() == (tmp_path / "two" / rel).read_bytes()
    text = (tmp_path / "one" / "regime-review.json").read_text()
    assert "NaN" not in text and "Infinity" not in text
    assert manifests[0]["scientificStatus"] == "EXPLORATORY_POST_OUTCOME_REGIME_DIAGNOSTIC"


# --------------------------------------------------------------------------- #
# Authorization and lifecycle — every test builds its own synthetic repository
# --------------------------------------------------------------------------- #
class FakeGitHub:
    """A fake GitHub git-refs API. Only create (POST) and read (GET) exist; any other verb is a test failure."""
    def __init__(self, existing=(), head="abc123"):
        self.refs = {r: "0ld5ha" for r in existing}
        self.calls = []
        self.head = head

    def __call__(self, method, path, payload=None):
        self.calls.append((method, path))
        if method == "POST":
            if payload["ref"] in self.refs:
                return 422, {}
            self.refs[payload["ref"]] = payload["sha"]
            return 201, {}
        if method == "GET" and path.startswith("/git/matching-refs/"):
            prefix = "refs/" + path[len("/git/matching-refs/"):]
            return 200, [{"ref": r, "object": {"sha": v}} for r, v in sorted(self.refs.items()) if r.startswith(prefix)]
        if method == "GET":
            ref = "refs/" + path[len("/git/ref/"):]
            return (200, {"object": {"sha": self.refs[ref]}}) if ref in self.refs else (404, {})
        raise AssertionError("the lock may only be created and read, never " + method)


def action_env(**over):
    return {"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/main", "GITHUB_SHA": "abc123", "GH_TOKEN": "t",
            "GITHUB_REPOSITORY": "o/r", **over}


def no_lock():
    return False


def fake_git(head="abc123", override=None):
    def git(args, cwd):
        if args == ["rev-parse", "HEAD"]:
            return (head + "\n").encode()
        if args[0] == "show":
            return override if override is not None else (Path(cwd) / args[1].split(":", 1)[1]).read_bytes()
        raise AssertionError(args)
    return git


def good_env(s):
    return {"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_SHA": "abc123",
            "REGIME_INPUT_ARTIFACT": s["input"]["artifactName"], "REGIME_INPUT_RUN_ID": str(s["input"]["producingRunId"])}


def unsealed_repo(tmp_path):
    """Synthetic PRE-RESULT repository: the frozen spec + sidecar and the sealed predecessor files, and no regime-review
    result or marker. The real ROOT may be in any lifecycle state."""
    repo = tmp_path / "repo"
    s = spec()
    rels = [E.SPEC_PATH, str(Path(E.SPEC_PATH).with_suffix(".sha256")), "research_specs/kr-factor-anatomy-v1.sha256", *s["predecessor"]["files"].values()]
    for rel in rels:
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, repo / rel)
    assert not (repo / E.RESULT_PATH).exists() and not (repo / E.MARKER_PATH).exists()
    return repo


def test_execution_refuses_before_merged_main_authorization(tmp_path):
    s, sha = E.load_spec()
    repo = unsealed_repo(tmp_path)
    env = good_env(s)
    permit = E.authorize_execution(s, sha, repo, env, fake_git(), no_lock)
    assert isinstance(permit, E.ExecutionPermit) and permit.specSha256 == sha
    cases = [({"GITHUB_ACTIONS": "false"}, "REQUIRES_ACTIONS"), ({"GITHUB_REF": "refs/heads/research/kr-top120-regime-review-v1"}, "REQUIRES_MAIN"),
             ({"GITHUB_REF": "refs/pull/1/merge"}, "REQUIRES_MAIN"), ({"GITHUB_EVENT_NAME": "pull_request"}, "REQUIRES_WORKFLOW_DISPATCH"),
             ({"GITHUB_EVENT_NAME": "push"}, "REQUIRES_WORKFLOW_DISPATCH"), ({"GITHUB_SHA": "other"}, "NOT_THE_DISPATCHED_COMMIT"),
             ({"GITHUB_SHA": ""}, "NOT_THE_DISPATCHED_COMMIT"), ({"REGIME_INPUT_ARTIFACT": "kr-model-raw-replay-1"}, "INPUT_ARTIFACT_IDENTITY_MISMATCH"),
             ({"REGIME_INPUT_RUN_ID": "1"}, "INPUT_ARTIFACT_IDENTITY_MISMATCH"), ({"REGIME_INPUT_RUN_ID": ""}, "INPUT_ARTIFACT_IDENTITY_MISMATCH")]
    for change, message in cases:
        with pytest.raises(ValueError, match=message):
            E.authorize_execution(s, sha, repo, {**env, **change}, fake_git(), no_lock)
    with pytest.raises(ValueError, match="SPEC_NOT_COMMITTED_AT_HEAD"):
        E.authorize_execution(s, sha, repo, env, fake_git(override=b"{}"), no_lock)


def test_execution_refuses_if_a_result_or_marker_already_exists(tmp_path):
    s, sha = E.load_spec()
    repo = unsealed_repo(tmp_path)
    env = good_env(s)
    assert E.authorize_execution(s, sha, repo, env, fake_git(), no_lock)
    (repo / E.MARKER_PATH).write_text("{}")
    with pytest.raises(ValueError, match="EXECUTION_MARKER_ALREADY_COMMITTED"):
        E.authorize_execution(s, sha, repo, env, fake_git(), no_lock)
    (repo / E.MARKER_PATH).unlink()
    (repo / E.RESULT_PATH).write_text("{}")
    with pytest.raises(ValueError, match="REGIME_REVIEW_RESULT_ALREADY_COMMITTED"):
        E.authorize_execution(s, sha, repo, env, fake_git(), no_lock)


@pytest.mark.parametrize("key", ["result", "report", "manifest", "provenance"])
def test_execution_refuses_if_the_sealed_predecessor_changed(tmp_path, key):
    s, sha = E.load_spec()
    repo = unsealed_repo(tmp_path)
    target = repo / s["predecessor"]["files"][key]
    target.write_bytes(target.read_bytes() + b" ")
    with pytest.raises(ValueError, match="PREDECESSOR_IDENTITY_CHANGED: " + key):
        E.authorize_execution(s, sha, repo, good_env(s), fake_git(), no_lock)


def test_verify_mode_touches_no_outcome_and_the_runner_refuses_outside_actions(tmp_path):
    from scripts import run_kr_top120_regime_review_v1 as CLI
    report = CLI.run("verify", output=str(tmp_path / "v"))
    assert report["status"] == "VERIFIED" and report["historicalExecutionPerformed"] is False and report["stoppedBeforeOutcomes"] is True
    assert report["executeAuthorizedInThisEnvironment"] is False and (tmp_path / "v" / "verify.json").is_file()
    with pytest.raises(ValueError, match="FORMAL_EXECUTION_REQUIRES_ACTIONS"):
        CLI.run("execute", input_root=str(tmp_path / "missing"), output=str(tmp_path / "out"), env={})
    with pytest.raises(ValueError, match="UNREGISTERED_EXECUTION_MODE"):
        CLI.run("gates-only")


def test_every_outcome_path_refuses_without_a_permit(monkeypatch, tmp_path):
    s, sha = E.load_spec()

    def bomb(*a, **k):
        raise AssertionError("data read before authorization")
    for name in ("prepare", "input_identity", "load_sources"):
        monkeypatch.setattr(X, name, bomb)
    with pytest.raises(ValueError, match="OUTCOME_ACCESS_WITHOUT_PERMIT"):
        E.execute(tmp_path / "missing", tmp_path / "out", s, sha, None)
    with pytest.raises(ValueError, match="OUTCOME_ACCESS_WITHOUT_PERMIT"):
        E.execute(tmp_path / "missing", tmp_path / "out", s, sha, E.ExecutionPermit(sha, object()))     # forged permit
    with pytest.raises(ValueError, match="OUTCOME_ACCESS_WITHOUT_PERMIT"):
        E.attach_outcomes(pd.DataFrame(), {}, {}, s, None, E.Counters())
    assert E.Counters().zero()


# --------------------------------------------------------------------------- #
# The durable one-shot lock: nothing before the gates, before any outcome, never movable, never reopened
# --------------------------------------------------------------------------- #
def stub_pipeline(monkeypatch, tmp_path, panel, api, reasons=(), attach=None):
    """Replace every data-reading step with a stub so the ORDER of operations can be observed on synthetic data."""
    s, sha = E.load_spec()
    log = []
    monkeypatch.setattr(X, "input_identity", lambda root: {"sha256": s["input"]["identitySha256"]})
    monkeypatch.setattr(X, "load_spec", lambda root: ({"inputs": {}}, "v1"))
    monkeypatch.setattr(X, "prepare", lambda root, v1: {"features": panel, "schedule": sorted(set(panel.date)), "market": None})
    monkeypatch.setattr(AE, "load_memberships", lambda *a: None)
    monkeypatch.setattr(A, "assert_pit_membership", lambda *a: True)
    monkeypatch.setattr(E, "signal_time_panel", lambda bundle: bundle["features"])

    def gates(*a):
        log.append("gates")
        return list(reasons)
    monkeypatch.setattr(E, "readiness_gates", gates)

    def default_attach(panel_, bundle, v1, spec_, permit, counters, lock=None, sha_=None):
        E.require_lock(lock, sha_)
        log.append("attach_outcomes")
        log.append("lock_present=" + str(E.lock_ref(sha) in api.refs))
        counters.outcomeColumnCalls += 1
        return panel_
    monkeypatch.setattr(E, "attach_outcomes", attach or default_attach)
    return s, sha, log


def run_execute(s, sha, tmp_path, api, env=None):
    return E.execute(tmp_path / "in", tmp_path / "out", s, sha, E.ExecutionPermit(sha, E._PERMIT_TOKEN), ROOT,
                     action_env() if env is None else env, api)


def test_a_failed_readiness_gate_creates_no_durable_lock_and_reads_no_outcome(monkeypatch, tmp_path):
    api = FakeGitHub()
    s, sha, log = stub_pipeline(monkeypatch, tmp_path, make_panel(n_dates=3), api, reasons=["MARKET_CAP_UNAVAILABLE_FOR_DYNAMIC_EXCLUSION"])
    monkeypatch.setattr(A, "endpoint_returns", lambda *a, **k: (_ for _ in ()).throw(AssertionError("outcome read")))
    with pytest.raises(ValueError, match="READINESS_GATE_FAILED: MARKET_CAP_UNAVAILABLE"):
        run_execute(s, sha, tmp_path, api)
    assert api.calls == [] and api.refs == {} and log == ["gates"]                  # no lock call of any kind
    assert not (tmp_path / "out" / "execution-started.json").exists()
    failed = json.loads((tmp_path / "out" / "gates-failed.json").read_text())
    assert failed["counters"] == {"targetCalls": 0, "labelCalls": 0, "outcomeColumnCalls": 0, "analysisCalls": 0, "markerWrites": 0}


def test_the_lock_is_created_after_the_gates_and_before_the_first_outcome(monkeypatch, tmp_path):
    api = FakeGitHub()
    s, sha, log = stub_pipeline(monkeypatch, tmp_path, make_panel(n_dates=3), api)
    monkeypatch.setattr(R, "add_outcomes", lambda p, n: (_ for _ in ()).throw(RuntimeError("stop after the outcomes were attached")))
    with pytest.raises(RuntimeError, match="stop after the outcomes were attached"):
        run_execute(s, sha, tmp_path, api)
    assert log == ["gates", "attach_outcomes", "lock_present=True"]                  # gates, then lock, then outcomes
    assert api.refs == {E.STUDY_LOCK_REF: "abc123", E.lock_ref(sha): "abc123"} and [c[0] for c in api.calls].count("POST") == 2
    marker = json.loads((tmp_path / "out" / "execution-started.json").read_text())
    assert marker["outcomesReadBeforeThisMarker"] == 0 and marker["lockRef"] == E.lock_ref(sha) and marker["lockedMainSha"] == "abc123"
    with pytest.raises(FileExistsError):
        E.write_execution_marker(tmp_path / "out", s, sha, {"sha256": "x"}, E.Counters())


def test_no_outcome_function_runs_without_the_durable_lock(tmp_path):
    s, sha = E.load_spec()
    permit = E.ExecutionPermit(sha, E._PERMIT_TOKEN)
    for lock in (None, object(), E.ExecutionLock(sha, "abc123", "r", object()), E.ExecutionLock("0" * 64, "abc123", "r", E._LOCK_TOKEN)):
        with pytest.raises(ValueError, match="DURABLE_EXECUTION_LOCK_REQUIRED_BEFORE_ANY_OUTCOME"):
            E.attach_outcomes(pd.DataFrame(), {}, {}, s, permit, E.Counters(), lock, sha)
    assert E.claim_execution_lock(sha, action_env(), FakeGitHub()).specSha256 == sha


def test_an_existing_lock_refuses_execution_before_any_outcome(monkeypatch, tmp_path):
    s, sha = E.load_spec()
    api = FakeGitHub(existing=[E.lock_ref(sha)])
    _, _, log = stub_pipeline(monkeypatch, tmp_path, make_panel(n_dates=3), api)
    with pytest.raises(ValueError, match="EXECUTION_LOCK_ALREADY_EXISTS"):
        run_execute(s, sha, tmp_path, api)
    assert log == ["gates"] and api.refs == {E.lock_ref(sha): "0ld5ha"}              # untouched, never moved to the new commit, no second tag
    repo = unsealed_repo(tmp_path)
    with pytest.raises(ValueError, match="EXECUTION_LOCK_ALREADY_EXISTS"):
        E.authorize_execution(s, sha, repo, good_env(s), fake_git(), lambda: E.lock_exists(sha, action_env(), api))


def test_a_post_lock_failure_permanently_consumes_the_study(monkeypatch, tmp_path):
    api = FakeGitHub()
    s, sha, _ = stub_pipeline(monkeypatch, tmp_path, make_panel(n_dates=3), api)
    monkeypatch.setattr(R, "add_outcomes", lambda p, n: (_ for _ in ()).throw(RuntimeError("infrastructure failure after the lock")))
    with pytest.raises(RuntimeError, match="infrastructure failure"):
        run_execute(s, sha, tmp_path, api)
    assert E.lock_ref(sha) in api.refs and E.STUDY_LOCK_REF in api.refs              # the failure did not release anything
    repo = unsealed_repo(tmp_path)
    probe = lambda: E.lock_exists(sha, action_env(), api)                            # noqa: E731
    with pytest.raises(ValueError, match="EXECUTION_LOCK_ALREADY_EXISTS"):
        E.authorize_execution(s, sha, repo, good_env(s), fake_git(), probe)          # no result, no marker, no artifact: still refused
    with pytest.raises(ValueError, match="EXECUTION_LOCK_ALREADY_EXISTS"):
        E.claim_execution_lock(sha, action_env(GITHUB_SHA="another-main-sha"), api)
    assert api.refs[E.lock_ref(sha)] == "abc123"


def test_artifacts_and_their_expiry_are_irrelevant_to_the_permanent_lock():
    import inspect
    for fn in (E.lock_exists, E.claim_execution_lock, E.require_lock, E.lock_ref):                  # the lock never reads an artifact
        text = inspect.getsource(fn).lower()
        assert "artifact" not in text and "expir" not in text and "retention" not in text
    s, sha = E.load_spec()
    held = FakeGitHub(existing=[E.lock_ref(sha)])
    assert E.lock_exists(sha, action_env(), held) is True                            # nothing else is asked: no artifact listing exists
    assert all(path.startswith("/git/matching-refs/tags/") for _, path in held.calls)
    text = (ROOT / ".github/workflows/kr-top120-regime-review-v1.yml").read_text()
    guard = text[text.index("Main-only guard"):text.index("      - uses: actions/setup-python@v6", text.index("Main-only guard"))]
    assert "EXECUTION_LOCK_ALREADY_EXISTS" in guard and "-attempt-" not in guard      # attempt artifacts neither block nor reopen
    assert guard.index("EXECUTION_LOCK_ALREADY_EXISTS") < guard.index("RESULTS_ARTIFACT_ALREADY_EXISTS")


def test_a_lock_from_an_older_spec_sha_still_consumes_the_whole_study(monkeypatch, tmp_path):
    s, sha = E.load_spec()
    old_sha = "0ld5pec" + "0" * 57                                                  # a previous revision's spec SHA
    assert old_sha != sha
    api = FakeGitHub(existing=[E.lock_ref(old_sha)])                                 # old-spec lock exists, no result was sealed
    repo = unsealed_repo(tmp_path)
    assert not (repo / E.RESULT_PATH).exists() and not (repo / E.MARKER_PATH).exists()
    probe = lambda: E.lock_exists(sha, action_env(), api)                            # noqa: E731
    with pytest.raises(ValueError, match="EXECUTION_LOCK_ALREADY_EXISTS"):
        E.authorize_execution(s, sha, repo, good_env(s), fake_git(), probe)          # the CURRENT spec has no lock of its own
    assert E.lock_ref(sha) not in api.refs
    with pytest.raises(ValueError, match="EXECUTION_LOCK_ALREADY_EXISTS"):
        E.claim_execution_lock(sha, action_env(), api)                               # nor can the claim create one
    assert api.refs == {E.lock_ref(old_sha): "0ld5ha"} and all(m == "GET" for m, _ in api.calls)
    _, _, log = stub_pipeline(monkeypatch, tmp_path, make_panel(n_dates=3), api)
    with pytest.raises(ValueError, match="EXECUTION_LOCK_ALREADY_EXISTS"):
        run_execute(s, sha, tmp_path, api)
    assert log == ["gates"]                                                          # refused before any outcome
    only_study_level = FakeGitHub(existing=[E.STUDY_LOCK_REF])
    assert E.lock_exists(sha, action_env(), only_study_level) is True


def test_same_spec_duplicates_refuse_and_no_lock_leaves_authorization_possible(tmp_path):
    s, sha = E.load_spec()
    repo = unsealed_repo(tmp_path)
    clean = FakeGitHub()
    permit = E.authorize_execution(s, sha, repo, good_env(s), fake_git(), lambda: E.lock_exists(sha, action_env(), clean))
    assert isinstance(permit, E.ExecutionPermit) and clean.refs == {}                # authorization alone creates nothing
    other_prefix = FakeGitHub(existing=["refs/tags/some-other-study-execution-lock-" + sha, "refs/tags/kr-top120-regime-review-v1-x"])
    assert E.lock_exists(sha, action_env(), other_prefix) is False                   # only THIS study's prefix counts
    E.claim_execution_lock(sha, action_env(), clean)
    held = FakeGitHub(existing=list(clean.refs))
    with pytest.raises(ValueError, match="EXECUTION_LOCK_ALREADY_EXISTS"):
        E.authorize_execution(s, sha, repo, good_env(s), fake_git(), lambda: E.lock_exists(sha, action_env(), held))
    with pytest.raises(ValueError, match="EXECUTION_LOCK_ALREADY_EXISTS"):
        E.claim_execution_lock(sha, action_env(), clean)


def test_workflow_guard_refuses_any_lock_for_the_study_not_one_spec_sha():
    text = (ROOT / ".github/workflows/kr-top120-regime-review-v1.yml").read_text()
    guard = text[text.index("Main-only guard"):text.index("      - uses: actions/setup-python@v6", text.index("Main-only guard"))]
    assert "listMatchingRefs" in guard and "'-execution-lock'" in guard and "matching.data.length > 0" in guard
    assert "specSha" not in guard and "getRef({...context.repo, ref: 'tags/'" not in guard    # no exact-SHA lookup remains
    s = spec()
    assert "ANY ref under" in s["lifecycle"]["executionLock"]["studyLevel"]
    assert "ENTIRE kr-top120-regime-review-v1 study" in s["lifecycle"]["executionLock"]["postLockFailure"]


def test_the_lock_cannot_be_moved_overwritten_or_deleted():
    s, sha = E.load_spec()
    api = FakeGitHub()
    lock = E.claim_execution_lock(sha, action_env(), api)
    assert lock.ref == E.lock_ref(sha) == "refs/tags/kr-top120-regime-review-v1-execution-lock-" + sha
    assert E.STUDY_LOCK_REF == "refs/tags/kr-top120-regime-review-v1-execution-lock"
    assert (lock.specSha256, lock.mainSha) == (sha, "abc123") and api.refs[lock.ref] == api.refs[E.STUDY_LOCK_REF] == "abc123"
    before = dict(api.refs)
    for sha_main in ("abc123", "def456"):
        with pytest.raises(ValueError, match="EXECUTION_LOCK_ALREADY_EXISTS"):
            E.claim_execution_lock(sha, action_env(GITHUB_SHA=sha_main), api)
    assert api.refs == before                                                          # same commit or another: not overwritten
    assert {m for m, _ in api.calls} == {"POST", "GET"}                                # FakeGitHub raises on any other verb
    import inspect
    source = inspect.getsource(E.claim_execution_lock) + inspect.getsource(E.lock_exists)
    for verb in ('"PATCH"', '"PUT"', '"DELETE"'):
        assert verb not in source


def test_the_lock_must_point_at_the_authorized_commit_and_be_created_only_on_main():
    s, sha = E.load_spec()

    class Redirecting(FakeGitHub):
        def __call__(self, method, path, payload=None):
            status, body = super().__call__(method, path, payload)
            return (status, {"object": {"sha": "somewhere-else"}}) if method == "GET" and path.startswith("/git/ref/") and status == 200 else (status, body)
    with pytest.raises(ValueError, match="EXECUTION_LOCK_NOT_ON_THE_AUTHORIZED_COMMIT"):
        E.claim_execution_lock(sha, action_env(), Redirecting())
    for bad in (action_env(GITHUB_REF="refs/heads/research/kr-top120-regime-review-v1"), action_env(GITHUB_ACTIONS="false")):
        with pytest.raises(ValueError, match="FORMAL_EXECUTION_REQUIRES_ACTIONS_MAIN"):
            E.claim_execution_lock(sha, bad, FakeGitHub())
    with pytest.raises(ValueError, match="ATOMIC_EXECUTION_LOCK_NOT_CREATED"):
        E.claim_execution_lock(sha, action_env(), lambda m, p, d=None: (200, []) if m == "GET" else (500, {}))
    for body, outcome in (([{"ref": "x"}], True), ([], False)):
        assert E.lock_exists(sha, action_env(), lambda m, p, d=None, b=body: (200, b)) is outcome
    with pytest.raises(ValueError, match="EXECUTION_LOCK_STATE_UNVERIFIABLE"):
        E.lock_exists(sha, action_env(), lambda m, p, d=None: (404, {}))                 # not a listing: unverifiable, refuse
    for env in ({}, action_env(GH_TOKEN=""), action_env(GITHUB_REPOSITORY="")):
        with pytest.raises(ValueError, match="EXECUTION_LOCK_STATE_UNVERIFIABLE"):
            E.lock_exists(sha, env, FakeGitHub())
    with pytest.raises(ValueError, match="EXECUTION_LOCK_STATE_UNVERIFIABLE"):
        E.lock_exists(sha, action_env(), lambda m, p, d=None: (503, {}))                 # an ambiguous answer refuses


def test_workflow_permission_for_the_lock_is_minimal_and_job_scoped():
    text = (ROOT / ".github/workflows/kr-top120-regime-review-v1.yml").read_text()
    assert text.index("permissions:\n  contents: read\n  actions: read") < text.index("  frozen-machine:")
    execute = text[text.index("  execute:"):]
    assert "    permissions:\n      contents: write" in execute and "      actions: read" in execute
    assert "contents: write" not in text[:text.index("  execute:")]
    assert "GH_TOKEN: ${{ github.token }}" in execute and "--mode execute" in execute
    s = spec()
    lock = s["lifecycle"]["executionLock"]
    assert lock["neverUpdatedMovedOrDeleted"] is True and lock["onlyMethodsIssued"] == ["POST", "GET"]
    assert "PERMANENTLY CONSUMES" in lock["postLockFailure"] and "no existing execution lock tag" in s["execution"]["executeRequires"]
    assert not any("attempt" in str(v).lower() and "does not close" in str(v).lower() for v in s["lifecycle"].values())


def test_gate_function_reports_every_registered_reason():
    s = spec()
    panel = make_panel(n_dates=4)
    bundle = {"schedule": sorted(set(panel.date))}
    assert E.readiness_gates(panel, bundle, s) == []
    assert "NO_PIT_NAME_DATES" in E.readiness_gates(panel.iloc[0:0], bundle, s)
    assert "MISSING_SCHEDULED_SIGNAL_DATE" in E.readiness_gates(panel, {"schedule": bundle["schedule"] + ["2099-01-01"]}, s)
    assert "DUPLICATE_PIT_NAME_DATE" in E.readiness_gates(pd.concat([panel, panel.iloc[:1]]), bundle, s)
    assert any(r.startswith("FACTOR_COLUMNS_MISSING") for r in E.readiness_gates(panel.drop(columns=["logAdv60"]), bundle, s))
    assert "MARKET_CAP_UNAVAILABLE_FOR_DYNAMIC_EXCLUSION" in E.readiness_gates(panel.assign(marketCap=np.nan), bundle, s)
    assert "NO_SIGNAL_TIME_BENCHMARK_STATE" in E.readiness_gates(panel.assign(riskMultiplier=np.nan), bundle, s)


# --------------------------------------------------------------------------- #
# Workflow
# --------------------------------------------------------------------------- #
def test_workflow_runs_only_verify_on_pull_requests_and_executes_only_from_main_dispatch():
    text = (ROOT / ".github/workflows/kr-top120-regime-review-v1.yml").read_text()
    assert "pull_request:" in text and "workflow_dispatch:" in text and "schedule" not in text
    execute = text[text.index("  execute:"):]
    assert "github.event_name == 'workflow_dispatch' && inputs.mode == 'execute'" in execute and "refs/heads/main" in execute
    assert "--mode execute" in execute and text.count("--mode execute") == 1 and "--mode execute" not in text[:text.index("  execute:")]
    for guard in ("SPEC_NOT_COMMITTED_AT_HEAD", "PREDECESSOR_IDENTITY_CHANGED", "INPUT_ARTIFACT_IDENTITY_MISMATCH", "REGIME_REVIEW_ALREADY_SEALED",
                  "REGIME_REVIEW_MARKER_ALREADY_COMMITTED", "PRESERVED_ARTIFACT_IDENTITY_MISMATCH", "RESULTS_ARTIFACT_ALREADY_EXISTS", "MAIN_HEAD_CHANGED"):
        assert guard in execute
    assert "permissions:\n  contents: read\n  actions: read" in text
    assert "kr_factor_anatomy" not in text and "run_kr_factor_anatomy_v1" not in text
    assert "-attempt-" in text and "-results-" in text


def test_the_new_workflow_is_documented_and_the_predecessor_workflow_is_unchanged():
    assert "kr-top120-regime-review-v1.yml" in (ROOT / "docs/workflow-inventory-addendum.md").read_text()
    a = json.loads((ROOT / "research_specs/kr-factor-anatomy-v1.json").read_text())
    rel = ".github/workflows/kr-factor-anatomy-v1.yml"
    assert hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == a["dependencyHashes"][rel]


# --------------------------------------------------------------------------- #
# Endpoint assembly parity with the anatomy, on a tiny synthetic bundle
# --------------------------------------------------------------------------- #
def test_outcome_assembly_equals_the_anatomy_assembly_on_a_synthetic_bundle():
    s, _ = E.load_spec()
    v1_spec, _ = X.load_spec(ROOT)
    days = RC.sessions("2013-01-01", "2028-12-31", "KR")
    sessions = days[(days >= "2020-01-01")][:900]
    rng = np.random.default_rng(1)
    prices = {t: pd.DataFrame({"Close": 100 * np.exp(np.cumsum(rng.normal(0, .01, len(sessions))))}, index=sessions)
              for t in ("000001.KS", "000002.KS", s["benchmark"])}
    sig = [str(sessions[i].date()) for i in (10, 30, 700)]
    features = pd.DataFrame({"ticker": ["000001.KS", "000002.KS", "000001.KS"], "date": sig})

    class Market:
        def at(self, ticker, date):
            return {"marketCap": 1e12}
    bundle = {"features": features, "prices": prices, "market": Market(), "accounting": {}, "schedule": sig,
              "overlay": {d: {"riskMultiplier": 1.0, "trendAdverse": False, "volAdverse": False} for d in sig}}
    permit = E.ExecutionPermit("x", E._PERMIT_TOKEN)
    lock = E.ExecutionLock("x", "abc123", "refs/tags/x", E._LOCK_TOKEN)
    mine = E.attach_outcomes(E.signal_time_panel(bundle), bundle, v1_spec, s, permit, E.Counters(), lock, "x")
    theirs = AE.build_panel(bundle, v1_spec, json.loads((ROOT / AE.SPEC_PATH).read_text()), AE.ExecutionPermit("x", AE._PERMIT_TOKEN), AE.Counters())
    shared = [c for c in mine.columns if c in theirs.columns and c.endswith(("126", "252")) and not c.startswith(("rel", "fundamental"))]
    assert {"entry126", "exit126", "stock126", "bench126", "status126", "rawStatus252"} <= set(shared)
    pd.testing.assert_frame_equal(mine[shared], theirs[shared], check_dtype=False)
    for col in ("marketCap", "riskMultiplier", "netIncomeImprovementToAssets"):
        pd.testing.assert_series_equal(mine[col], theirs[col], check_dtype=False)
    assert {"trendAdverse", "volAdverse"} <= set(mine.columns)
