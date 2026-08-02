import unittest

import numpy as np
import pandas as pd

from pipeline import kelly_portfolio as KP
from pipeline import ledger as LG


def _outcome(date, excess=0.02, percentile=92, region="US", horizon=5):
    return {
        "id": f"{date}|{region}|AAA|v1", "date": date, "ticker": "AAA",
        "region": region, "alpha": 99.0, "alphaPercentile": percentile,
        "horizons": {str(horizon): {"excessReturn": excess, "fwdReturn": excess}},
    }


def _candidates(n=6):
    rows = []
    for i in range(n):
        rows.append({
            "ticker": f"T{i}", "region": "US" if i % 2 else "KR",
            "sector": f"S{i % 3}", "alpha": 1000 - i,
            "alphaPercentile": 92, "longTermResearchView": "POSITIVE",
            "valueTrap": False, "modelSleeveWeightPct": 15.0,
            "evidenceCoverage": 0.9, "dataCompleteness": 0.9,
            "risk": {"vol252Pct": 20 + i},
            "entry": {"entryState": "ACCUMULATE_GRADUALLY"},
        })
    return rows


class KellyPortfolioTests(unittest.TestCase):
    def test_expected_returns_use_only_matured_ledger_and_not_alpha_score(self):
        dates = pd.bdate_range("2025-01-02", periods=40, freq="5B")
        rows = [_outcome(d.strftime("%Y-%m-%d")) for d in dates[:6]]
        # This enormous future outcome must not enter a replay as of 2025-10-01.
        rows.append(_outcome("2025-09-29", excess=0.99))
        cfg = {"horizonDays": 5, "minEffectiveDates": 3,
               "minUniqueDates": 3, "shrinkagePriorStrength": 3,
               "activation": {"minPaperDays": 0, "minMaturedSignals": 0},
               "alphaPercentileBuckets": [0, 60, 80, 90, 95, 100],
               "transactionCosts": {"US": {"commissionBps": 5, "sellTaxBps": 3,
                                               "spreadBps": 10, "assumedTurnoverPct": 25,
                                               "rebalanceDays": 5}}}
        got = KP.estimate_expected_returns(
            [{"ticker": "X", "region": "US", "alpha": -9999, "alphaPercentile": 92}],
            rows, cfg, as_of="2025-10-01")[0]
        self.assertEqual(got["status"], "SHADOW")
        self.assertAlmostEqual(got["rawObservedExcessReturnPct"], 2.0)
        self.assertLess(got["expectedExcessReturnPct"], 2.0)

    def test_insufficient_history_shrinks_expected_return_to_zero(self):
        cfg = {"horizonDays": 5, "minEffectiveDates": 10,
               "minUniqueDates": 5, "activation": {"minPaperDays": 0, "minMaturedSignals": 0},
               "alphaPercentileBuckets": [0, 90, 100]}
        got = KP.estimate_expected_returns(
            [{"ticker": "X", "region": "US", "alphaPercentile": 95}],
            [_outcome("2025-01-02", percentile=95)], cfg, as_of="2026-01-01")[0]
        self.assertEqual(got["status"], "SHADOW_INSUFFICIENT_HISTORY")
        self.assertEqual(got["expectedExcessReturnPct"], 0.0)

    def test_effective_sample_does_not_count_same_day_cross_section_as_independent(self):
        rows = [_outcome("2025-01-02") for _ in range(100)]
        effective, non_overlapping = KP._effective_sample_size(rows, 126)
        self.assertEqual(non_overlapping, 1)
        self.assertLess(effective, len(rows))

    def test_sample_covariance_is_symmetric_and_psd(self):
        rng = np.random.default_rng(7)
        idx = pd.bdate_range("2024-01-01", periods=320)
        common = rng.normal(0, 0.01, len(idx))
        prices = {}
        for i in range(3):
            ret = common * 0.8 + rng.normal(0, 0.003, len(idx))
            close = pd.Series(100 * np.exp(np.cumsum(ret)), index=idx)
            prices[f"T{i}"] = pd.DataFrame({"Close": close})
        cov, meta = KP.estimate_covariance(
            prices, list(prices), {"covarianceMinDays": 252,
                                   "covarianceLookbackDays": 300,
                                   "useLedoitWolf": False})
        self.assertEqual(meta["status"], "READY")
        self.assertTrue(np.allclose(cov, cov.T))
        self.assertGreaterEqual(float(np.linalg.eigvalsh(cov).min()), -1e-10)

    def test_entry_state_and_research_guards(self):
        cfg = {"watchWeightMultiplier": 0.5, "waitForPullbackWeightMultiplier": 0.25}
        base = {"longTermResearchView": "POSITIVE", "entry": {"entryState": "WATCH"}}
        self.assertEqual(KP._state_multiplier(base, cfg), 0.5)
        self.assertEqual(KP._state_multiplier({**base, "entry": {"entryState": "WAIT_FOR_PULLBACK"}}, cfg), 0.25)
        self.assertEqual(KP._state_multiplier({**base, "entry": {"entryState": "EVENT_RISK"}}, cfg), 0.0)
        self.assertEqual(KP._state_multiplier({**base, "valueTrap": True}, cfg), 0.0)

    def test_constraints_leave_excess_as_cash(self):
        candidates = _candidates(6)
        cfg = {"maxPositionWeight": 0.10, "maxSectorWeight": 0.20,
               "maxThemeWeight": 0.20, "minCashPct": 10,
               "regionCaps": {"KR": 0.45, "US": 0.45}, "blendWeight": 0.25}
        themes = {c["ticker"]: ["Crowded"] if c["ticker"] in {"T0", "T1", "T2"} else ["Other"]
                  for c in candidates}
        got = KP.blend_with_risk_weighted_portfolio(
            {c["ticker"]: 0.2 for c in candidates},
            {c["ticker"]: 0.2 for c in candidates}, candidates, cfg, themes)
        w = got["weights"]
        self.assertLessEqual(float(w.max()), 0.10 + 1e-9)
        self.assertLess(float(w.sum()), 0.90)  # clipped capital remains cash
        sector, theme, region = KP._exposures(w, candidates, themes)
        self.assertLessEqual(max(sector.values()), 0.20 + 1e-9)
        self.assertLessEqual(max(theme.values()), 0.20 + 1e-9)
        self.assertLessEqual(max(region.values()), 0.45 + 1e-9)

    def test_no_ledger_history_keeps_risk_weighted_shadow_fallback(self):
        candidates = _candidates(6)
        long_term = {"regions": {"ALL": {"picks": candidates}}}
        cfg = {"enabled": True, "mode": "shadow", "minNames": 6, "maxNames": 12,
               "maxPositionWeight": 0.10, "maxSectorWeight": 0.25,
               "maxThemeWeight": 0.20, "minCashPct": 10,
               "regionCaps": {"KR": 0.65, "US": 0.65},
               "regimeMultipliers": {"Transition/Low confidence": {"kellyMultiplier": 0.5, "minCashPct": 20}}}
        got = KP.build_model_portfolio(long_term, {}, [], cfg,
                                       macro_regime={"regime": "Transition/Low confidence", "confidence": 0.4})
        self.assertEqual(got["status"], "SHADOW_INSUFFICIENT_HISTORY")
        self.assertEqual(got["fallbackReason"], "expected_return_history_insufficient")
        self.assertAlmostEqual(sum(got["finalWeights"].values()) + got["cashPct"] / 100, 1.0)
        self.assertFalse(got["kellyApplied"])
        self.assertEqual(got["constrainedKellyWeights"], {})
        self.assertEqual(got["kellyAllocationImpactPct"], 0.0)
        self.assertTrue(all(p["constrainedKellyWeightPct"] is None for p in got["positions"]))

    def test_serialized_weights_and_cash_sum_to_100pct_after_rounding(self):
        weights = pd.Series({"A": 0.123456, "B": 0.234567, "C": 0.345653})
        serialized, cash_pct = KP._serialize_allocation(weights)
        legacy_cash_pct = round((1.0 - float(weights.sum())) * 100.0, 2)

        self.assertGreater(abs(sum(serialized.values()) + legacy_cash_pct / 100.0 - 1.0), 1e-5)
        self.assertLessEqual(abs(sum(serialized.values()) + cash_pct / 100.0 - 1.0), 1e-8)

    def test_blocked_portfolio_hides_all_weights(self):
        got = KP.build_model_portfolio({"regions": {}}, {}, [], {"enabled": True}, blocked=True)
        self.assertEqual(got["status"], "BLOCKED")
        self.assertEqual(got["positions"], [])
        self.assertEqual(got["finalWeights"], {})

    def test_portfolio_ledger_is_append_only_by_date_and_model(self):
        payload = {
            "modelVersion": "v1", "schemaVersion": "2.2.0", "meta": {"latestDataDate": "2026-01-02"},
            "modelPortfolio": {"status": "SHADOW_READY", "positions": [], "cashPct": 20,
                               "finalWeights": {"AAA": 0.8}},
        }
        first = LG.portfolio_record_from_payload(payload)
        merged, appended, _ = LG.append_portfolio_signals([], [first])
        changed = dict(first); changed["cashPct"] = 99
        merged2, appended2, skipped2 = LG.append_portfolio_signals(merged, [changed])
        self.assertEqual((appended, appended2, skipped2), (1, 0, 1))
        self.assertEqual(merged2[0]["cashPct"], 20)

    def test_portfolio_outcome_uses_matured_common_calendar(self):
        idx = pd.bdate_range("2025-01-02", periods=80)
        a = pd.Series(np.linspace(100, 120, len(idx)), index=idx)
        b = pd.Series(np.linspace(100, 110, len(idx)), index=idx)
        bench = pd.Series(np.linspace(100, 108, len(idx)), index=idx)
        signal = {
            "id": "2025-01-02|PORTFOLIO|v1", "date": "2025-01-02", "modelVersion": "v1",
            "finalWeights": {"A": 0.45, "B": 0.45},
            "riskWeightedWeights": {"A": 0.4, "B": 0.5},
            "constrainedKellyWeights": {"A": 0.5, "B": 0.3},
            "regionExposure": {"US": 90.0}, "benchmarks": {"US": "SPY"},
            "estimatedTurnover": 10.0,
        }
        got = LG.compute_portfolio_outcomes(
            [signal], {"A": pd.DataFrame({"Close": a}), "B": pd.DataFrame({"Close": b})},
            {"SPY": bench})
        self.assertTrue(got and "21" in got[0]["horizons"])
        metrics = got[0]["horizons"]["21"]
        self.assertGreater(metrics["portfolioReturn"], 0)
        self.assertIsNotNone(metrics["costAdjustedExcessReturn"])
        self.assertTrue(metrics["transactionCostFallbackUsed"])

    def test_portfolio_outcome_uses_serialized_regional_cost_policy(self):
        idx = pd.bdate_range("2025-01-02", periods=40)
        close = pd.Series(np.linspace(100, 110, len(idx)), index=idx)
        signal = {
            "id": "2025-01-02|PORTFOLIO|v1", "date": "2025-01-02",
            "finalWeights": {"A": .8}, "regionExposure": {"US": 80.0},
            "estimatedTurnover": 25.0, "benchmarks": {"US": "SPY"},
            "transactionCostPolicy": {"US": {
                "commissionBps": 4, "spreadBps": 8, "sellTaxBps": 2,
            }},
        }
        outcomes = LG.compute_portfolio_outcomes(
            [signal], {"A": pd.DataFrame({"Close": close})}, {"SPY": close})
        metrics = outcomes[0]["horizons"]["21"]
        expected_cost = .25 * (4 * 2 + 8 * 2 + 2) / 10_000
        assert metrics["transactionCost"] == round(expected_cost, 6)
        assert metrics["transactionCostFallbackUsed"] is False

    def test_active_covariance_matches_regional_benchmark_basis(self):
        rng = np.random.default_rng(71)
        idx = pd.bdate_range("2024-01-02", periods=180)
        benchmark_returns = rng.normal(0.0002, 0.012, len(idx))
        benchmark = pd.Series(100 * np.exp(np.cumsum(benchmark_returns)), index=idx)
        prices = {}
        active_returns = {}
        for i, ticker in enumerate(("A", "B", "C")):
            active = rng.normal(0.0001 * i, 0.003 + i * 0.0005, len(idx))
            active_returns[ticker] = active
            prices[ticker] = pd.DataFrame({"Close": 100 * np.exp(np.cumsum(benchmark_returns + active))}, index=idx)

        cov, meta = KP.estimate_active_covariance(
            prices, list(prices), benchmark,
            {"covarianceMinDays": 120, "covarianceLookbackDays": 160, "useLedoitWolf": False},
            region="US", benchmark="SPY",
        )

        assert meta["status"] == "READY"
        assert meta["returnBasis"] == "REGIONAL_ACTIVE"
        assert meta["region"] == "US" and meta["benchmark"] == "SPY"
        expected = pd.DataFrame(active_returns, index=idx).iloc[1:].tail(160).cov() * 252
        assert np.allclose(cov.to_numpy(), expected.to_numpy(), atol=2e-4)

    def test_regional_active_covariances_are_kept_separate(self):
        idx = pd.bdate_range("2024-01-02", periods=100)
        us_bench = pd.Series(np.linspace(100, 120, len(idx)), index=idx)
        kr_bench = pd.Series(np.linspace(100, 90, len(idx)), index=idx)
        prices = {
            "U1": pd.DataFrame({"Close": us_bench * np.linspace(1, 1.05, len(idx))}),
            "U2": pd.DataFrame({"Close": us_bench * np.linspace(1, 1.03, len(idx))}),
            "K1": pd.DataFrame({"Close": kr_bench * np.linspace(1, 1.04, len(idx))}),
            "K2": pd.DataFrame({"Close": kr_bench * np.linspace(1, 1.02, len(idx))}),
        }
        cfg = {"covarianceMinDays": 60, "covarianceLookbackDays": 90, "useLedoitWolf": False}
        _, us_meta = KP.estimate_active_covariance(prices, ["U1", "U2"], us_bench, cfg, region="US", benchmark="SPY")
        _, kr_meta = KP.estimate_active_covariance(prices, ["K1", "K2"], kr_bench, cfg, region="KR", benchmark="^KS200")
        assert (us_meta["region"], us_meta["benchmark"]) == ("US", "SPY")
        assert (kr_meta["region"], kr_meta["benchmark"]) == ("KR", "^KS200")
        assert us_meta["returnBasis"] == kr_meta["returnBasis"] == "REGIONAL_ACTIVE"

    def test_sample_gate_is_shared_and_reports_every_shortfall(self):
        cfg = {"minEffectiveDates": 8, "minUniqueDates": 12,
               "activation": {"minPaperDays": 30, "minMaturedSignals": 20}}
        gate = KP.sample_gate(paper_days=29, matured_signals=19, effective_dates=7,
                              unique_dates=11, cfg=cfg)
        assert gate["eligible"] is False
        assert gate["method"] == "DATE_CLUSTERED_NEWEY_WEST_HAC"
        assert gate["missing"] == ["paperDays", "maturedSignals", "effectiveDates", "uniqueDates"]

    def test_alpha_bucket_calibration_repairs_non_monotonic_expectations(self):
        dates = pd.bdate_range("2025-01-02", periods=12)
        outcomes = []
        for date in dates:
            outcomes.append(_outcome(date.strftime("%Y-%m-%d"), excess=.03, percentile=70, horizon=5))
            outcomes.append(_outcome(date.strftime("%Y-%m-%d"), excess=.01, percentile=92, horizon=5))
        cfg = {
            "horizonDays": 5, "minEffectiveDates": 2, "minUniqueDates": 5,
            "shrinkagePriorStrength": 2, "timeDecayHalfLifeDays": 100,
            "activation": {"minPaperDays": 0, "minMaturedSignals": 0},
            "alphaPercentileBuckets": [0, 60, 80, 90, 95, 100],
            "transactionCosts": {"US": {"commissionBps": 0, "sellTaxBps": 0,
                                           "spreadBps": 0, "assumedTurnoverPct": 0,
                                           "rebalanceDays": 5}},
        }
        got = KP.estimate_expected_returns([
            {"ticker": "LOW", "region": "US", "alphaPercentile": 70},
            {"ticker": "HIGH", "region": "US", "alphaPercentile": 92},
        ], outcomes, cfg, as_of="2025-06-30")
        by_ticker = {row["ticker"]: row for row in got}
        assert by_ticker["LOW"]["preIsotonicExpectedExcessReturnPct"] > by_ticker["HIGH"]["preIsotonicExpectedExcessReturnPct"]
        assert by_ticker["LOW"]["expectedExcessReturnPct"] <= by_ticker["HIGH"]["expectedExcessReturnPct"]
        assert by_ticker["HIGH"]["monotonicityWarning"] == "BUCKET_MONOTONICITY_REPAIRED"
        assert by_ticker["HIGH"]["confidenceIntervalPct"] is not None
        assert "topSectorSharePct" in by_ticker["HIGH"]["distortionDiagnostics"]

    def test_transaction_cost_uses_turnover_region_spread_and_rebalance(self):
        cfg = {"horizonDays": 126, "transactionCosts": {"US": {
            "commissionBps": 4, "sellTaxBps": 2, "spreadBps": 8,
            "assumedTurnoverPct": 30, "rebalanceDays": 63,
            "expectedTradeNotionalKrw": 5000000,
        }}}
        detail = KP.estimate_transaction_cost({"ticker": "A", "region": "US"}, cfg)
        expected = 0.30 * (4 * 2 + 8 * 2 + 2) / 10_000 * 2
        assert detail["estimatedCost"] == expected
        assert detail["assumedTurnoverPct"] == 30
        assert detail["rebalanceDays"] == 63
        assert detail["expectedTradeNotionalKrw"] == 5000000

    def test_equal_return_candidate_cut_is_input_order_invariant(self):
        candidates = _candidates(8)
        tickers = [c["ticker"] for c in candidates]
        covariance = pd.DataFrame(np.eye(8) * 0.04, index=tickers, columns=tickers)
        expected = [{"ticker": t, "expectedExcessReturnPct": 2.0, "status": "SHADOW"} for t in tickers]
        cfg = {"horizonDays": 126, "maxNames": 6, "minNames": 6,
               "maxPositionWeight": .2, "maxSectorWeight": .6, "maxThemeWeight": .6,
               "minCashPct": 0, "regionCaps": {"KR": 1, "US": 1}}
        first = KP.optimize_fractional_kelly(expected, covariance, candidates, cfg, .25)
        second = KP.optimize_fractional_kelly(list(reversed(expected)), covariance,
                                              list(reversed(candidates)), cfg, .25)
        assert first["ok"] and second["ok"]
        assert first["weights"].to_dict() == second["weights"].to_dict()
        assert list(first["weights"].index) == ["T0", "T1", "T2", "T3", "T4", "T5"]

    def test_fraction_blend_currency_and_allocation_impact_are_distinct(self):
        candidates = _candidates(6)
        long_term = {"regions": {
            "KR": {"picks": [c for c in candidates if c["region"] == "KR"]},
            "US": {"picks": [c for c in candidates if c["region"] == "US"]},
        }}
        idx = pd.bdate_range("2025-01-02", periods=100)
        rng = np.random.default_rng(811)
        bench_returns = {"KR": rng.normal(.0001, .008, len(idx)), "US": rng.normal(.0002, .009, len(idx))}
        bench = {r: pd.Series(100 * np.exp(np.cumsum(ret)), index=idx) for r, ret in bench_returns.items()}
        prices = {}
        for i, c in enumerate(candidates):
            ret = bench_returns[c["region"]] + rng.normal(.0001 * (6 - i), .004, len(idx))
            prices[c["ticker"]] = pd.DataFrame({"Close": 100 * np.exp(np.cumsum(ret))}, index=idx)
        outcome_dates = pd.bdate_range("2025-01-02", periods=15)
        outcomes = []
        for region in ("KR", "US"):
            for i, date in enumerate(outcome_dates):
                outcomes.append(_outcome(date.strftime("%Y-%m-%d"), excess=.01 + i * .0002,
                                         region=region, horizon=5))
        cfg = {
            "enabled": True, "mode": "shadow", "horizonDays": 5,
            "kellyFraction": .25, "blendWeight": .25,
            "minEffectiveDates": 2, "minUniqueDates": 5,
            "shrinkagePriorStrength": 2, "timeDecayHalfLifeDays": 100,
            "activation": {"minPaperDays": 10, "minMaturedSignals": 5},
            "alphaPercentileBuckets": [0, 90, 95, 100],
            "covarianceMinDays": 60, "covarianceLookbackDays": 90, "useLedoitWolf": False,
            "maxPositionWeight": .2, "maxSectorWeight": .5, "maxThemeWeight": .5,
            "minCashPct": 10, "maxTurnoverPct": 100, "minNames": 6,
            "minNamesPerRegion": 3, "maxNames": 6, "regionCaps": {"KR": .65, "US": .65},
            "currency": {"baseCurrency": "KRW", "fxReturnsIncluded": False, "fxHedged": False},
            "transactionCosts": {r: {"commissionBps": 0, "sellTaxBps": 0, "spreadBps": 0,
                                      "assumedTurnoverPct": 0, "rebalanceDays": 5} for r in ("KR", "US")},
            "regimeMultipliers": {"Transition/Low confidence": {"kellyMultiplier": .5, "minCashPct": 20}},
        }
        validation = {"paperDays": 40, "maturedSignals": 100,
                      "regionIC": {"KR": {"mean": .1}, "US": {"mean": .1}},
                      "costAdjustedExcessReturn": .01, "noMddDeterioration": True,
                      "firstSignalDate": "2025-01-02"}
        got = KP.build_model_portfolio(
            long_term, prices, outcomes, cfg,
            macro_regime={"regime": "Transition/Low confidence", "confidence": 1},
            as_of="2025-06-30", validation_status=validation,
            benchmarks={"KR": "^KS200", "US": "SPY"}, bench_by_region=bench,
        )
        assert got["status"] == "SHADOW_READY"
        assert got["kellyApplied"] is True
        assert got["baseKellyFraction"] == .25
        assert got["appliedKellyFraction"] == .125
        assert got["kellyBlendWeight"] == .25
        assert got["currencyPolicy"]["baseCurrency"] == "KRW"
        assert got["currencyPolicy"]["warning"] == "FX_RISK_NOT_IN_ACTIVE_COVARIANCE"
        assert got["covariance"]["returnBasis"] == "REGIONAL_ACTIVE"
        risk = pd.Series(got["riskWeightedWeights"])
        final = pd.Series(got["finalWeights"]).reindex(risk.index, fill_value=0)
        expected_impact = .5 * ((final - risk).abs().sum() + abs((1 - final.sum()) - (1 - risk.sum()))) * 100
        assert got["kellyAllocationImpactPct"] == round(expected_impact, 2)
        assert abs(sum(got["finalWeights"].values()) + got["cashPct"] / 100 - 1) <= 1e-8
        shuffled_long_term = {"regions": {
            region: {"picks": list(reversed(blob["picks"]))}
            for region, blob in long_term["regions"].items()
        }}
        replay = KP.build_model_portfolio(
            shuffled_long_term, prices, list(reversed(outcomes)), cfg,
            macro_regime={"regime": "Transition/Low confidence", "confidence": 1},
            as_of="2025-06-30", validation_status=validation,
            benchmarks={"KR": "^KS200", "US": "SPY"}, bench_by_region=bench,
        )
        assert replay["finalWeights"] == got["finalWeights"]
        assert replay["cashPct"] == got["cashPct"]


if __name__ == "__main__":
    unittest.main()
