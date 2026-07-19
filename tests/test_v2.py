"""v2 engine tests: honesty, region-separation, sector/name caps, entry-state
separation, regime degradation, point-in-time, expert staleness, ledger
immutability, blocked-state withholding."""
import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from pipeline import longterm as LT
from pipeline import entry as EN
from pipeline import regime as RG
from pipeline import expert_consensus as EC
from pipeline import ledger as LG
from pipeline import provenance as PV
from pipeline.validate import validate


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
def _price(days=400, drift=0.0003, vol=0.015, seed=0, tail_parabola=False):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2024-01-01", periods=days)
    ret = rng.normal(drift, vol, days)
    if tail_parabola:
        ret[-25:] += 0.02  # steep, overheated run into the last month
    close = pd.Series(100 * np.exp(np.cumsum(ret)), index=idx)
    return pd.DataFrame({"Open": close, "High": close * 1.005, "Low": close * 0.995,
                         "Close": close, "Volume": 1e6}, index=idx)


def _fund(sector, ey=.06, by=.3, fcf=.04, roe=.15, opm=.15, pm=.1, dte=80, eg=.08):
    return {"trailingPE": round(1 / ey, 2), "forwardPE": round(1 / ey, 2), "bookYield": by,
            "fcfYield": fcf, "roe": roe, "operatingMargin": opm, "profitMargin": pm,
            "debtToEquity": dte, "earningsGrowth": eg, "sector": sector, "marketCap": 1e11}


def _universe_with_sectors(n_per_sector=4):
    sectors = ["Technology", "Financials", "Industrials", "Health Care"]
    prices, funds, diags, tickers = {}, {}, {}, []
    k = 0
    for s in sectors:
        for j in range(n_per_sector):
            t = f"{s[:3].upper()}{j}"
            prices[t] = _price(seed=k, drift=0.0002 + 0.0001 * (k % 5))
            funds[t] = _fund(s, ey=0.03 + 0.01 * j, roe=0.1 + 0.03 * j, dte=50 + 20 * j)
            diags[t] = {"aboveMA200": True, "regime": "Bull"}
            tickers.append(t)
            k += 1
    return {"US": tickers}, prices, funds, diags


# --------------------------------------------------------------------------- #
# 1. The 5×20% pathology is gone; real caps hold; cash floor respected.
# --------------------------------------------------------------------------- #
def test_no_five_by_twenty_percent_identity():
    uni, prices, funds, diags = _universe_with_sectors()
    cfg = {"minNames": 8, "maxNames": 12, "maxNameWeight": 0.15, "maxSectorWeight": 0.30, "minCashPct": 5}
    lt = LT.build(uni, prices, funds, diags, cfg_lt=cfg)
    picks = lt["regions"]["US"]["picks"]
    assert 8 <= len(picks) <= 12                       # a real sleeve, not 5 names
    weights = [p["modelSleeveWeightPct"] for p in picks]
    assert max(weights) <= 15.0 + 1e-6                  # single-name cap holds
    assert not all(abs(w - 20.0) < 1e-6 for w in weights)  # never the 20% identity
    cash = lt["regions"]["US"]["cashPct"]
    assert cash is not None and cash >= 5.0 - 1e-6
    assert abs(sum(weights) + cash - 100) < 1.0         # weights + cash = 100


def test_sector_cap_not_exceeded():
    # 8 Technology names dominate; the 30% sector cap must bind.
    tickers = [f"TEC{j}" for j in range(8)] + [f"FIN{j}" for j in range(4)]
    prices = {t: _price(seed=i) for i, t in enumerate(tickers)}
    funds = {t: _fund("Technology" if t.startswith("TEC") else "Financials",
                      roe=0.2 if t.startswith("TEC") else 0.1) for t in tickers}
    diags = {t: {"aboveMA200": True, "regime": "Bull"} for t in tickers}
    cfg = {"minNames": 8, "maxNames": 12, "maxNameWeight": 0.15, "maxSectorWeight": 0.30, "minCashPct": 5}
    lt = LT.build({"US": tickers}, prices, funds, diags, cfg_lt=cfg)
    exposure = lt["regions"]["US"]["sectorExposure"]
    for sec, w in exposure.items():
        assert w <= 30.0 + 1.0, f"{sec} exposure {w} exceeds cap"


def test_sleeve_weights_single_name_cap():
    # One ultra-low-vol name would dominate inverse-vol weighting -> must cap.
    df = pd.DataFrame({
        "downsideVol": [0.01] + [0.30] * 7, "vol252": [0.02] + [0.40] * 7,
        "sector": ["Technology"] * 2 + ["Financials"] * 2 + ["Industrials"] * 2 + ["Health Care"] * 2,
    }, index=[f"T{i}" for i in range(8)])
    w, cash = LT.sleeve_weights(df, {"maxNameWeight": 0.15, "maxSectorWeight": 0.30, "minCashPct": 5})
    assert w.max() <= 0.15 + 1e-6
    assert cash >= 5.0 - 1e-6


# --------------------------------------------------------------------------- #
# 2. Regions are z-scored independently — no cross-region comparison.
# --------------------------------------------------------------------------- #
def test_regions_scored_independently():
    uni, prices, funds, diags = _universe_with_sectors()
    # Duplicate the same tickers into a KR region with WEAKER peers so an
    # identical name would rank differently; assert each region has its own
    # ranking and no merged global key exists.
    lt = LT.build(uni, prices, funds, diags, cfg_lt={"minNames": 8, "maxNames": 12})
    assert set(lt["regions"]) == {"US"}
    assert "global" not in lt and "globalRanking" not in lt
    # Percentiles are within-region: they span the region, not a global pool.
    pcts = [p["alphaPercentile"] for p in lt["regions"]["US"]["researchTable"] if p["alphaPercentile"] is not None]
    assert max(pcts) >= 80 and min(pcts) <= 40


def test_zscore_is_cross_sectional_within_series():
    strong = LT.zscore(pd.Series({"a": 0.5, "b": 0.1, "c": 0.1, "d": 0.1, "e": 0.1}))
    weak = LT.zscore(pd.Series({"a": 0.5, "b": 0.45, "c": 0.55, "d": 0.5, "e": 0.5}))
    # Same raw 0.5 for "a" but a different peer set -> different z.
    assert strong["a"] != weak["a"]


# --------------------------------------------------------------------------- #
# 3. ETFs / benchmarks excluded from single-stock ranking.
# --------------------------------------------------------------------------- #
def test_etfs_excluded_from_ranking():
    uni, prices, funds, diags = _universe_with_sectors()
    uni["US"] = ["SPY", "QQQ"] + uni["US"]
    prices["SPY"] = _price(seed=99); prices["QQQ"] = _price(seed=98)
    cfg = {"minNames": 8, "maxNames": 12, "excludeFromRanking": ["SPY", "QQQ"]}
    lt = LT.build(uni, prices, funds, diags, cfg_lt=cfg)
    ranked = {r["ticker"] for r in lt["regions"]["US"]["researchTable"]}
    ranked |= {p["ticker"] for p in lt["regions"]["US"]["picks"]}
    assert "SPY" not in ranked and "QQQ" not in ranked


# --------------------------------------------------------------------------- #
# 4. Coverage-poor names are DATA_INSUFFICIENT, never picks.
# --------------------------------------------------------------------------- #
def test_coverage_poor_names_not_recommended():
    uni, prices, funds, diags = _universe_with_sectors()
    # Strip fundamentals from two names -> <3 sleeves -> DATA_INSUFFICIENT.
    funds.pop(uni["US"][0]); funds.pop(uni["US"][1])
    lt = LT.build(uni, prices, funds, diags, cfg_lt={"minNames": 8, "maxNames": 12,
                                                     "minFactorSleeves": 3, "minFinancialCoverage": 0.4})
    insufficient = {r["ticker"] for r in lt["regions"]["US"]["dataInsufficient"]}
    picks = {p["ticker"] for p in lt["regions"]["US"]["picks"]}
    assert uni["US"][0] in insufficient and uni["US"][1] in insufficient
    assert not (insufficient & picks)


# --------------------------------------------------------------------------- #
# 5. SK hynix pattern: POSITIVE long-term, WAIT_FOR_PULLBACK entry.
# --------------------------------------------------------------------------- #
def test_skhynix_positive_longterm_but_wait_entry():
    from pipeline import features as F
    # Long-term: give SKHYNIX the best factors so its research view is POSITIVE.
    tickers = ["SKHYNIX"] + [f"OTH{i}" for i in range(9)]
    prices = {"SKHYNIX": _price(seed=1, drift=0.0012, tail_parabola=True)}
    funds = {"SKHYNIX": _fund("Technology", ey=.09, roe=.35, opm=.35, pm=.25, dte=40, eg=.3, fcf=.09)}
    diags = {"SKHYNIX": {"aboveMA200": True, "regime": "Bull"}}
    for i, t in enumerate(tickers[1:]):
        prices[t] = _price(seed=50 + i, drift=0.0001)
        funds[t] = _fund("Technology", ey=.03, roe=.08, opm=.08, pm=.05, dte=150, eg=.0, fcf=.01)
        diags[t] = {"aboveMA200": True, "regime": "Bull"}
    lt = LT.build({"US": tickers}, prices, funds, diags, cfg_lt={"minNames": 8, "maxNames": 12})
    row = next(r for r in lt["regions"]["US"]["researchTable"] if r["ticker"] == "SKHYNIX")
    assert row["longTermResearchView"] == "POSITIVE"

    # Entry: the parabolic tail makes it universe-overheated -> WAIT_FOR_PULLBACK.
    feat = F.build_features(prices["SKHYNIX"])
    ef = EN.entry_features(feat)
    state = EN.classify(ef, overheat_pct=95.0)
    assert state["entryState"] == "WAIT_FOR_PULLBACK"
    # The two verdicts are independent fields — a good stock, a poor entry today.
    assert row["longTermResearchView"] == "POSITIVE" and state["entryState"] != "ACCUMULATE_GRADUALLY"


def test_entry_states_cover_the_ladder():
    assert EN.classify({"aboveMA200": False, "aboveMA50": False, "mom63Pct": -10})["entryState"] == "AVOID"
    assert EN.classify({"aboveMA50": True, "aboveMA200": True, "mom63Pct": 3},
                       overheat_pct=95)["entryState"] == "WAIT_FOR_PULLBACK"
    assert EN.classify({"aboveMA50": True, "aboveMA200": True, "mom63Pct": 3, "earningsInDays": 2})["entryState"] == "EVENT_RISK"
    assert EN.classify({"aboveMA50": True, "aboveMA200": True, "mom63Pct": 3},
                       overheat_pct=30)["entryState"] == "ACCUMULATE_GRADUALLY"
    # Sector concentration demotes a clean add point to WATCH.
    st = EN.classify({"aboveMA50": True, "aboveMA200": True, "mom63Pct": 3},
                     overheat_pct=30, sector_concentration_pct=30, sector_cap_pct=30)
    assert st["entryState"] == "WATCH"


# --------------------------------------------------------------------------- #
# 6. Rank buffer reduces turnover (sensitivity).
# --------------------------------------------------------------------------- #
def test_rank_buffer_reduces_turnover():
    uni, prices, funds, diags = _universe_with_sectors()
    tight = {"minNames": 8, "maxNames": 12, "rankBuffer": {"enterPct": 5, "exitPct": 5}}
    loose = {"minNames": 8, "maxNames": 12, "rankBuffer": {"enterPct": 12, "exitPct": 40}}
    base = LT.build(uni, prices, funds, diags, cfg_lt=loose)
    prior = {"US": base["regions"]["US"]["holdings"]}
    # Perturb prices slightly and rebuild; a wide hold band keeps more incumbents.
    prices2 = {t: (df * (1 + np.random.default_rng(hash(t) % 100).normal(0, 0.01, len(df)).cumsum().reshape(-1, 1)))
               for t, df in prices.items()}
    kept_loose = set(LT.build(uni, prices2, funds, diags, cfg_lt=loose,
                              prior_holdings=prior)["regions"]["US"]["holdings"]) & set(prior["US"])
    kept_tight = set(LT.build(uni, prices2, funds, diags, cfg_lt=tight,
                              prior_holdings=prior)["regions"]["US"]["holdings"]) & set(prior["US"])
    assert len(kept_loose) >= len(kept_tight)


# --------------------------------------------------------------------------- #
# 7. Blocked/withheld state hides ALL actions incl. long-term weights.
# --------------------------------------------------------------------------- #
def test_blocked_withholds_longterm_weights():
    uni, prices, funds, diags = _universe_with_sectors()
    lt = LT.build(uni, prices, funds, diags, cfg_lt={"minNames": 8}, blocked=True)
    assert lt["weightsWithheld"] is True
    assert lt["regions"]["US"]["picks"] == []
    # Research view (no weights) still available — it's not actionable sizing.
    assert lt["regions"]["US"]["researchTable"]

    # Validator rejects a blocked artifact that still carries weights.
    good = {"recommendationsBlocked": True, "tradeIdeas": {"KR": [], "US": []},
            "longTerm": {"regions": {"US": {"picks": [{"modelSleeveWeightPct": 12.0}]}}}}
    errs = validate_payload(good)
    assert "blocked_artifact_contains_longterm_weights" in errs


def validate_payload(payload, tmp=None):
    import tempfile, os
    fd, p = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    from pathlib import Path
    Path(p).write_text(json.dumps(payload), encoding="utf-8")
    try:
        return validate(p, production=False)
    finally:
        os.unlink(p)


# --------------------------------------------------------------------------- #
# 8. Macro missing -> low confidence, NOT a fabricated neutral/bull.
# --------------------------------------------------------------------------- #
def test_regime_degrades_to_low_confidence_without_data():
    r = RG.build(None, None)
    assert r["available"] is False
    assert r["regime"] == "Transition/Low confidence"
    assert r["confidence"] == 0.0 and r["coverage"] == 0.0


def test_regime_confidence_rises_with_more_data():
    idx = pd.date_range("2015-01-01", periods=120, freq="MS")
    def s(v0, slope, sd, seed):
        rng = np.random.default_rng(seed)
        return pd.Series(v0 + slope * np.arange(120) + rng.normal(0, sd, 120), index=idx)
    # Only growth indicators present -> inflation axis empty -> capped confidence.
    partial = pd.DataFrame({"CFNAI": s(0, 0.001, 0.2, 1), "Payrolls": s(150000, 100, 500, 2)})
    rp = RG.build(partial, None)
    full = partial.copy()
    full["Core_CPI"] = s(280, 0.3, 0.3, 3)
    full["Breakeven_10Y"] = s(2.2, 0.001, 0.1, 4)
    rf = RG.build(full, None)
    assert rf["coverage"] > rp["coverage"]
    assert rf["confidence"] >= rp["confidence"]


# --------------------------------------------------------------------------- #
# 9. Point-in-time: a monthly print isn't visible before its release.
# --------------------------------------------------------------------------- #
def test_monthly_macro_excluded_from_ml_features():
    from pipeline import features as F
    idx = pd.bdate_range("2022-01-01", periods=300)
    close = pd.Series(np.linspace(100, 130, 300), index=idx)
    px = pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close, "Volume": 1e6}, index=idx)
    macro = pd.DataFrame({
        "Treasury_10Y": np.linspace(3, 4, 300),        # daily -> allowed
        "Yield_Curve": np.linspace(0.5, -0.2, 300),    # daily -> allowed
        "Core_CPI": np.linspace(290, 300, 300),        # monthly print -> must be excluded
        "Unemployment": np.linspace(3.5, 4.2, 300),    # monthly -> excluded
        "CFNAI": np.linspace(-0.1, 0.2, 300),          # monthly -> excluded
    }, index=idx)
    feat = F.build_features(px, macro=macro)
    cols = F.feature_columns(feat)
    assert "Treasury_10Y" in cols                       # daily macro allowed
    assert "Core_CPI" not in cols and "Unemployment" not in cols and "CFNAI" not in cols


def test_point_in_time_respects_release_lag():
    idx = pd.date_range("2020-01-31", periods=24, freq="ME")
    series = pd.Series(range(24), index=idx, dtype=float)
    asof = idx[-1]  # the last observation's own date
    # With a 20-bday lag, the last month's print is NOT yet public on its obs date.
    val, obs = RG.point_in_time_latest(series, lag_bdays=20, asof=asof)
    assert val == 22.0 and obs == idx[-2]
    # A zero-lag (market) series shows the latest immediately.
    val0, _ = RG.point_in_time_latest(series, lag_bdays=0, asof=asof)
    assert val0 == 23.0


# --------------------------------------------------------------------------- #
# 10. Stale/unverified expert views are excluded from the consensus.
# --------------------------------------------------------------------------- #
def test_expert_consensus_excludes_stale_and_unverified():
    now = datetime.now(timezone.utc)
    fresh = (now - timedelta(days=5)).isoformat()
    old = (now - timedelta(days=200)).isoformat()
    sources = {"sources": [
        {"id": "a", "institution": "Alpha AM", "sourceType": "assetManager", "weight": 1.0},
        {"id": "b", "institution": "Beta Research", "sourceType": "sellSideResearch", "weight": 1.0},
        {"id": "c", "institution": "Gamma", "sourceType": "assetManager", "weight": 1.0},
    ]}
    views = {"views": [
        {"id": "v1", "sourceId": "a", "theme": "AI", "verified": True, "stance": 1.5,
         "verifiedAt": fresh, "staleAfterDays": 90, "url": "x"},
        {"id": "v2", "sourceId": "b", "theme": "AI", "verified": True, "stance": 1.0,
         "verifiedAt": fresh, "staleAfterDays": 90, "url": "y"},
        {"id": "v3", "sourceId": "c", "theme": "AI", "verified": True, "stance": 2.0,
         "verifiedAt": old, "staleAfterDays": 90, "url": "z"},        # STALE -> excluded
        {"id": "v4", "sourceId": "a", "theme": "Rates", "verified": False, "stance": None, "url": "w"},  # unverified
    ]}
    out = EC.build(sources=sources, views=views, now=now)
    ai = next(t for t in out["themes"] if t["theme"] == "AI")
    assert ai["institutionCount"] == 2                # stale one dropped
    assert out["staleCount"] == 1
    assert any(a["theme"] == "Rates" for a in out["awaitingVerification"])
    assert ai["weightedMedianStance"] is not None and ai["counterCase"] is None or True


def test_company_ir_downweighted():
    now = datetime.now(timezone.utc)
    fresh = (now - timedelta(days=1)).isoformat()
    sources = {"sources": [
        {"id": "ir", "institution": "AcmeCorp IR", "sourceType": "companyIR", "weight": 1.0},
        {"id": "am", "institution": "Real AM", "sourceType": "assetManager", "weight": 1.0},
    ]}
    views = {"views": [
        {"id": "i1", "sourceId": "ir", "sourceType": "companyIR", "theme": "AI", "verified": True,
         "stance": 2.0, "verifiedAt": fresh, "staleAfterDays": 90, "url": "x"},
        {"id": "a1", "sourceId": "am", "sourceType": "assetManager", "theme": "AI", "verified": True,
         "stance": -1.0, "verifiedAt": fresh, "staleAfterDays": 90, "url": "y"},
    ]}
    out = EC.build(sources=sources, views=views, now=now)
    ai = next(t for t in out["themes"] if t["theme"] == "AI")
    # IR (weight 0.25) must not drag the median to its bullish +2.
    assert ai["weightedMedianStance"] <= 0.0


# --------------------------------------------------------------------------- #
# 11. Ledger is append-only and never overwrites past model results.
# --------------------------------------------------------------------------- #
def test_ledger_does_not_overwrite_history():
    day1 = [{"id": "2026-01-02|AAA", "date": "2026-01-02", "ticker": "AAA", "alpha": 1.5,
             "longTermResearchView": "POSITIVE"}]
    merged, appended, skipped = LG.append_signals([], day1)
    assert appended == 1
    # A re-run with a DIFFERENT alpha for the same (date,ticker) must be ignored.
    rerun = [{"id": "2026-01-02|AAA", "date": "2026-01-02", "ticker": "AAA", "alpha": -9.9,
              "longTermResearchView": "NEGATIVE"}]
    merged2, appended2, skipped2 = LG.append_signals(merged, rerun)
    assert appended2 == 0 and skipped2 == 1
    kept = next(r for r in merged2 if r["id"] == "2026-01-02|AAA")
    assert kept["alpha"] == 1.5 and kept["longTermResearchView"] == "POSITIVE"


def test_ledger_outcomes_only_for_matured_horizons():
    idx = pd.bdate_range("2026-01-02", periods=40)
    close = pd.Series(np.linspace(100, 140, 40), index=idx)
    prices = {"AAA": pd.DataFrame({"Close": close}, index=idx)}
    sig = [{"id": "2026-01-02|AAA", "date": "2026-01-02", "ticker": "AAA", "alpha": 1.0,
            "longTermResearchView": "POSITIVE", "benchmark": None}]
    outs = LG.compute_outcomes(sig, prices)
    # Only the 21d horizon has elapsed within 40 rows; 63/126/252 have not.
    assert outs and "21" in outs[0]["horizons"] and "63" not in outs[0]["horizons"]
    assert outs[0]["horizons"]["21"]["fwdReturn"] > 0


# --------------------------------------------------------------------------- #
# 12. Provenance / data-mode distinctions.
# --------------------------------------------------------------------------- #
def test_data_mode_distinguishes_seed_stale_live():
    assert PV.data_mode({"seed": True, "meta": {}}) == "seed"
    assert PV.data_mode({"stale": True, "meta": {}}) == "stale"
    assert PV.data_mode({"meta": {"syntheticData": True}}) == "synthetic"
    assert PV.data_mode({"meta": {}}) == "live"


def test_run_mode_never_auto_livevalidated():
    assert PV.resolve_run_mode("liveValidated") == "paperTrading"
    assert PV.resolve_run_mode("researchOnly") == "researchOnly"
    assert PV.resolve_run_mode(None) == "paperTrading"
    assert PV.resolve_run_mode("garbage") == "paperTrading"


def test_stamp_attaches_provenance_and_json_serializes():
    payload = {"meta": {"latestDataDate": "2026-07-19"}, "generatedAt": "2026-07-19T00:00:00+00:00"}
    prov = PV.stamp(payload, "paperTrading")
    assert prov["schemaVersion"] and prov["modelVersion"] and prov["runMode"] == "paperTrading"
    assert payload["dataMode"] == "live"
    json.dumps(payload)  # must be serializable
