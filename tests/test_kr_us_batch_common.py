"""Safeguards for paired samples, strict matching and matured-only decisions."""
import numpy as np
import pandas as pd
import pytest

from research.kr_us_strategy_batch_v1 import common as C


def test_block_statistics_preserve_gaps_and_match_explicit_draws():
    v = np.linspace(-0.08, 0.12, 180)
    mask = np.zeros(180, dtype=bool)
    mask[:35] = True
    mask[120:160] = True
    got = C.stats(v, 126, mask)
    rng = np.random.default_rng(C.SEED)
    starts = rng.integers(0, len(v) - 25 + 1, size=(4000, int(np.ceil(len(v) / 25))))
    idx = (starts[:, :, None] + np.arange(25)).reshape(4000, -1)[:, :len(v)]
    sampled = np.where(mask, v, np.nan)[idx]
    n = np.isfinite(sampled).sum(axis=1)
    mean = np.nansum(sampled, axis=1)[n > 0] / n[n > 0]
    assert got["n"] == 75
    assert got["ci"] == pytest.approx(np.quantile(mean, [0.025, 0.975]))
    assert got["pOneSided"] == (1 + (mean <= 0).sum()) / (1 + len(mean))
    assert C.stats(v[mask], 126)["ci"] != pytest.approx(got["ci"])
    assert C.stats([np.nan] * 120, 252)["mean"] is None
    assert C.stats(np.ones(99), 252)["ci"] is None


def test_strict_match_is_one_to_one_excludes_held_and_keeps_weights():
    f = pd.DataFrame({"industry": ["x"] * 6, "_mcap": [100, 105, 101, 90, 400, np.nan]},
                     index=["held1", "held2", "peer1", "peer2", "tooBig", "unknown"])
    book, audit = C.match_book(f, {"held1": 0.08, "held2": 0.12, "ETF": 0.8}, "ETF",
                               order=["held1", "held2"])
    assert book == {"peer1": 0.08, "peer2": 0.12, "ETF": 0.8}
    assert [a["peer"] for a in audit] == ["peer1", "peer2"]
    failed, partial = C.match_book(f.drop(index="peer2"),
                                   {"held1": 0.08, "held2": 0.12, "ETF": 0.8}, "ETF",
                                   order=["held1", "held2"])
    assert failed is None
    assert partial[0]["reason"] == "MATCHED"
    assert partial[1]["reason"] == "NO_PEER_WITHIN_CAP_CALIPER"
    assert partial[1]["peer"] is None


def test_caliper_is_applied_before_nearest_and_endpoints_included():
    f = pd.DataFrame({"industry": ["x"] * 3, "_mcap": [100, 200, 201]}, index=["h", "a", "b"])
    b, a = C.match_book(f, {"h": 0.2, "ETF": 0.8}, "ETF")
    assert b["a"] == 0.2
    assert a[0]["capRatio"] == 2
    assert C.match_book(f.drop(index="a"), {"h": 0.2, "ETF": 0.8}, "ETF")[0] is None


def test_policy_uses_strictly_matured_common_and_rejects_deeper_drawdown():
    dates = pd.date_range("2015-01-02", periods=330, freq="W-FRI")
    r = pd.DataFrame({"safe": 0.02, "unsafe": 0.20}, index=dates)
    md = pd.DataFrame({"safe": -0.08, "unsafe": -0.20}, index=dates)
    em = pd.Series(-0.10, index=dates)
    ex = pd.Series(dates + pd.Timedelta(days=182), index=dates)
    meta = {"safe": {"q": 0.2, "k": 5}, "unsafe": {"q": 1, "k": None}}
    got = C.choose_policy(r, md, em, ex, dates, meta, list(meta))
    sufficient = [f for f in got["fits"] if f["sufficient"]]
    assert sufficient
    assert set(got["choices"]) == {"ETF", "safe"}
    for f in sufficient:
        fit = pd.Timestamp(f["fitDate"])
        assert pd.Timestamp(f["maxTrainExit"]) < fit
        assert f["nTrain"] == int((ex < fit).sum())
        assert not f["candidateFits"][1]["riskGuard"]
    fit = pd.Timestamp(sufficient[0]["fitDate"])
    changed = r.copy()
    changed.loc[ex >= fit] = -100
    after = C.choose_policy(changed, md, em, ex, dates, meta, list(meta))
    assert next(f for f in after["fits"] if pd.Timestamp(f["fitDate"]) == fit) == sufficient[0]
    assert got["choices"].loc[dates[dates.year == fit.year]].nunique() == 1


def test_nav_gap_split_and_unresolved_prices_are_not_dropped():
    dates = pd.date_range("2020-01-01", periods=300, freq="B")
    n = pd.Series(np.exp(np.arange(300) * 0.0003), index=dates)
    b = pd.Series(np.exp(np.arange(300) * 0.0002), index=dates)
    out = C.nav_window(n, b)
    assert out["cagr"] == pytest.approx((n.iloc[-1] / n.iloc[0]) ** (252 / 299) - 1)
    assert out["annualization"] == "252_SESSIONS_FROZEN_ENGINE"
    assert out["annualArithmeticDailyGap"] + out["compoundingRemainder"] == pytest.approx(out["cagrGap"])
    assert out["mdd"] == 0
    n.iloc[40] = np.nan
    with pytest.raises(ValueError, match="unresolved"):
        C.nav_window(n, b)


def test_holm_keeps_unavailable_slots_and_hash_is_reproducible():
    adjusted = C.holm({"a": 0.01, "b": None, "c": 0.04})
    assert adjusted == {"a": 0.03, "c": 0.08, "b": 1.0}
    tickers = ["1", "2", "3", "4", "5"]
    assert C.neutral_order(tickers, "2020-01-03", "KR") == C.neutral_order(tickers[::-1], "2020-01-03", "KR")


def test_integrated_families_do_not_shrink_when_a_market_is_unavailable(tmp_path, monkeypatch):
    from research.kr_us_strategy_batch_v1 import report as R
    monkeypatch.setattr(R, "OUT", tmp_path)
    sample = {"n": 110, "mean": 0.02, "ci": [0.01, 0.03], "pOneSidedApprox": 0.001}
    claim = "ETF:KR:S2:SLOT20:K5"
    summaries = {"KR": {"coreComparisons": {"126": {claim: sample}},
                         "fixed": {"126": {"KR:S2:SLOT20:K5": {"common": sample}}}}}
    core, broad = R.make_families(summaries)
    assert len(core) == 82 and len(broad) == 230
    assert next(r for r in core if r["id"] == claim and r["horizon"] == 126)["pHolm"] == pytest.approx(0.041)
    assert next(r for r in broad if r["id"] == "KR:S2:SLOT20:K5" and r["horizon"] == 126)["pHolm"] == pytest.approx(0.115)
    assert all(r["pUsedInFamily"] == 1 for r in core if r["market"] == "US")
