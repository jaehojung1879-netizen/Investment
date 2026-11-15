"""Synthetic tests for research/us_selection_value_v1 (no market data) and the KR OCI price correction."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from research.us_selection_value_v1 import evaluate as EV

ROOT = Path(__file__).resolve().parents[1]


def cross_section(n=40, seed=0):
    rng = np.random.default_rng(seed)
    sectors = ["Information Technology", "Health Care", "Industrials", "Energy"]
    x = pd.DataFrame({
        "ticker": [f"T{i:02d}" for i in range(n)],
        "sector": [sectors[i % 4] for i in range(n)],
        "momentum252": rng.normal(0.1, 0.2, n), "vol252": rng.uniform(0.15, 0.5, n),
        "cashOperatingProfitability": rng.normal(0.08, 0.05, n), "operatingProfitabilityToAssets": rng.normal(0.07, 0.05, n),
        "assetGrowthPct": rng.normal(5, 10, n), "debtToEquity": rng.uniform(0.2, 3, n),
        "netIncomeTTM": rng.normal(1e9, 8e8, n), "operatingCashFlowTTM": rng.normal(1.5e9, 1e9, n),
        "operatingCashFlowTTMPrior": rng.normal(1.4e9, 1e9, n), "equity": rng.normal(5e9, 4e9, n),
        "marketCap": rng.uniform(5e9, 5e11, n), "inCommonUniverse": True, "identity": "PIT_SINGLE_CIK"})
    return x


def test_spec_is_frozen_and_lists_every_strategy():
    spec = json.loads((ROOT / "research/us_selection_value_v1/spec.json").read_text())
    assert set(spec["strategies"]) == set(EV.STRATS)
    assert spec["costs"].startswith("pipeline.benchmark_alpha.REALISTIC_COSTS")
    assert {k: list(v) for k, v in EV.PERIODS.items() if k != "ALL"} == spec["periods"]   # the frozen periods, unchanged
    assert set(EV.PERIODS) - set(spec["periods"]) == {"ALL"}                               # the whole window is the only addition


def test_books_respect_size_sector_cap_and_ticker_ties():
    x = EV.score(EV.common(cross_section()))
    top5 = EV.book(x, "PRICE", "TOP5")
    assert len(top5) == 5 and max(pd.Series([x.at[t, "sector"] for t in top5]).value_counts()) <= 2
    q = EV.book(x, "PRICE", "TOP_QUINTILE")
    assert len(q) == int(np.ceil(len(x) / 5))
    basket = EV.book(x, "SECTOR_MOMENTUM_BASKET", "TOP5")
    assert len({x.at[t, "sector"] for t in basket}) == 1
    best = x.groupby("sector")["momentum252"].mean().idxmax()
    assert x.at[basket[0], "sector"] == best
    # a tie is broken by ticker, not by input order
    y = x.copy()
    y["PRICE"] = 0.5
    assert EV.book(y, "PRICE", "TOP5")[0] == min(EV.book(y, "PRICE", "TOP_QUINTILE"))


def test_confirmed_strategies_only_hold_confirmed_names():
    x = EV.score(EV.common(cross_section(seed=3)))
    for s in ("VALUE_CONFIRMED", "PRICE_CONFIRMED"):
        for b in ("TOP5", "TOP_QUINTILE"):
            assert all(bool(x.at[t, "confirmed"]) for t in EV.book(x, s, b))
    ok = (x["netIncomeTTM"] > 0) & (x["operatingCashFlowTTM"] > 0) & (x["operatingCashFlowTTM"] > x["operatingCashFlowTTMPrior"])
    assert (x["confirmed"] == ok).all()


def test_within_sector_value_is_sector_relative():
    x = EV.score(EV.common(cross_section(seed=5)))
    for _, g in x.groupby("sector"):
        assert g["WITHIN_SECTOR_VALUE"].between(0, 1).all()
    # doubling every market cap in one sector leaves that sector's value ranks unchanged
    base = EV.common(cross_section(seed=5))
    moved = base.copy()
    moved.loc[moved["sector"] == "Energy", "marketCap"] *= 2
    a, b = EV.score(base), EV.score(moved)
    pd.testing.assert_series_equal(a["WITHIN_SECTOR_VALUE"], b["WITHIN_SECTOR_VALUE"])


def test_attribution_is_an_exact_identity():
    x = EV.score(EV.common(cross_section(seed=7)))
    rng = np.random.default_rng(1)
    r = pd.Series(rng.normal(0.05, 0.2, len(x)), index=x.index)
    names = EV.book(x, "WITHIN_SECTOR_VALUE", "TOP_QUINTILE")
    att = EV.attribution(x, names, r)
    gross = float(r.loc[names].mean())
    assert gross - att["universeEW"] == pytest.approx(att["sectorAllocation"] + att["withinSectorSelection"], abs=1e-12)


def test_costs_are_charged_on_entry_and_exit():
    assert EV.net(0.0) == pytest.approx((1 - EV.BUY) * (1 - EV.SELL) - 1)
    assert EV.BUY == pytest.approx(8.0e-4) and EV.SELL == pytest.approx(8.3e-4)


def test_block_ci_needs_enough_observations():
    assert EV.block_ci([0.1, 0.2], 5) is None
    lo, hi = EV.block_ci(list(np.linspace(-0.1, 0.1, 100)), 5)
    assert lo < 0 < hi


def test_as_traded_close_undoes_later_splits_only():
    from research.us_selection_value_v1.features import AsTraded
    at = AsTraded.__new__(AsTraded)
    idx = pd.to_datetime(["2020-01-02", "2020-06-01", "2021-01-04"])
    at.series = {"X": pd.Series([10.0, 12.0, 13.0], index=idx)}
    at.splits = {"X": [(pd.Timestamp("2020-03-01"), 4.0)]}
    assert at.close_on("X", pd.Timestamp("2020-01-02")) == pytest.approx(40.0)   # before the 4:1 split: as traded = 4 x adjusted
    assert at.close_on("X", pd.Timestamp("2020-06-01")) == pytest.approx(12.0)
    assert at.close_on("X", pd.Timestamp("2020-02-03")) is None                  # no neighbouring-session substitution


def test_greedy_nonoverlap_counts_disjoint_cohorts():
    d = list(pd.date_range("2020-01-03", periods=60, freq="W-FRI"))
    assert EV.greedy_nonoverlap(d, 26) == 3


def _oci():
    spec = importlib.util.spec_from_file_location("oci_mod_test", ROOT / "research/alpha_mechanism_decomposition_v1/kr_followup/oci_corrected_nav.py")
    # importing the module pulls the vendored engine; only corrected_closes is exercised
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_oci_correction_sets_the_relisting_return_and_leaves_later_returns():
    rec = json.loads((ROOT / "research/alpha_mechanism_decomposition_v1/kr_followup/010060-corporate-action-reconciliation.json").read_text())
    t = rec["timeline"]
    days = pd.to_datetime([t["lastTradeBeforeHalt"], t["haltFirst"], t["relisting"], "2023-05-31", "2023-06-01"])
    replay = rec["holderReturnLastTradeToRelistingClose"]["replayV16Conditional"]
    closes = pd.DataFrame({"010060.KS": [100.0, 100.0, 100 * (1 + replay), 100 * (1 + replay) * 1.02, 100 * (1 + replay) * 1.03],
                           "069500.KS": 1.0}, index=days)
    fixed, k = _oci().corrected_closes(closes, rec)
    econ = rec["holderReturnLastTradeToRelistingClose"]["economicBothSecurities"]
    assert fixed["010060.KS"].iloc[2] / fixed["010060.KS"].iloc[0] - 1 == pytest.approx(econ, abs=1e-12)
    later = fixed["010060.KS"].pct_change().iloc[3:]
    pd.testing.assert_series_equal(later, closes["010060.KS"].pct_change().iloc[3:])
    assert (fixed["069500.KS"] == 1.0).all()


def test_block_length_follows_the_spec_h_over_five_weeks():
    from research.us_selection_value_v1 import followup as FU
    assert FU.spec_block(126) == 25 and FU.spec_block(252) == 50
    rows = [{"date": f"2020-01-{i % 28 + 1:02d}", "names": 5, "gross": 0.0, "net": 0.0, "spyNet": 0.0, "netExcessSPY": 0.01 * (i % 3 - 1),
             "netExcessQQQ": 0.0, "largeCapAndUniverse": 0.0, "sectorAllocation": 0.0, "withinSectorSelection": 0.0, "costs": 0.0,
             "peerSelection": 0.0, "overlap": None} for i in range(40)]
    # 40 cohorts < 2 x 25-week blocks: the spec block cannot form an interval (the old 5-week block could)
    assert EV.summarise(rows, 126)["ciMeanNetExcessSPY"] is None
    assert EV.block_ci([r["netExcessSPY"] for r in rows], 5) is not None


def test_entry_exit_windows_split_on_the_actual_sessions():
    from research.us_selection_value_v1 import followup as FU
    e, x = pd.Timestamp("2022-06-01"), pd.Timestamp("2022-12-30")
    assert FU.in_window("EXIT_BY_2022", "2022-05-27", e, x) and not FU.in_window("ENTRY_FROM_2023", "2022-05-27", e, x)
    assert not FU.in_window("EXIT_BY_2022", "2022-08-05", e, pd.Timestamp("2023-02-03"))
    assert FU.in_window("ENTRY_FROM_2023", "2022-12-30", pd.Timestamp("2023-01-03"), x)
