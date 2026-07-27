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
        cfg = {"horizonDays": 5, "minEffectiveObservations": 3,
               "minNonOverlappingDates": 3, "shrinkagePriorStrength": 3,
               "alphaPercentileBuckets": [0, 60, 80, 90, 95, 100],
               "costHaircut": {"US": 0.004}}
        got = KP.estimate_expected_returns(
            [{"ticker": "X", "region": "US", "alpha": -9999, "alphaPercentile": 92}],
            rows, cfg, as_of="2025-10-01")[0]
        self.assertEqual(got["status"], "SHADOW")
        self.assertAlmostEqual(got["rawObservedExcessReturnPct"], 2.0)
        self.assertLess(got["expectedExcessReturnPct"], 2.0)

    def test_insufficient_history_shrinks_expected_return_to_zero(self):
        cfg = {"horizonDays": 5, "minEffectiveObservations": 10,
               "minNonOverlappingDates": 5, "alphaPercentileBuckets": [0, 90, 100]}
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


if __name__ == "__main__":
    unittest.main()
