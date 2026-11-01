"""Run directly with unittest; pytest also discovers these tests if explicitly selected."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("recovery_review", HERE / "review.py")
review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review)


class BoundaryTests(unittest.TestCase):
    def test_cost_bridge_and_unknown_attribution(self):
        a = review.accounting(0.10, 0.08, 0.07)
        self.assertAlmostEqual(a["passiveMinusNetCagrPp"], 3)
        self.assertAlmostEqual(a["grossMinusNetCostCagrPp"], 1)
        self.assertAlmostEqual(a["unattributedNonCostCagrPp"], 2)
        for key in ("delayedExitCagrPp", "falseAlarmCagrPp", "delayedReentryCagrPp"):
            self.assertIsNone(a[key])

    def test_sealed_source_tamper_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / review.KR
            path.parent.mkdir(parents=True)
            path.write_text('{"forged": true}\n')
            with self.assertRaisesRegex(ValueError, "HASH_MISMATCH"):
                review.sealed(Path(folder), review.KR)

    def test_observation_day_does_not_override_release_time(self):
        row = {"feature": "trans_vix_level", "observedAt": "2026-10-01T20:00:00+00:00",
               "availableAt": "2026-10-05T00:00:00+00:00", "value": 25}
        with self.assertRaisesRegex(ValueError, "NOT_KNOWN"):
            review.require_ex_ante([row], "2026-10-02T09:00:00+00:00")
        review.require_ex_ante([row], "2026-10-05T09:00:00+00:00")

    def test_timezone_conversion_and_missing_timezone(self):
        row = {"feature": "fast_realized_vol_21", "observedAt": "2026-10-02T15:30:00+09:00",
               "availableAt": "2026-10-02T18:00:00+09:00", "value": 100}
        review.require_ex_ante([row], "2026-10-02T09:00:00+00:00")
        with self.assertRaisesRegex(ValueError, "TIMEZONE_REQUIRED"):
            review.require_ex_ante([row], "2026-10-02T09:00:00")

    def test_oracle_metadata_cannot_be_smuggled_as_a_feature(self):
        row = {"feature": "fast_realized_vol_21", "observedAt": "2026-10-02T06:30:00+00:00",
               "availableAt": "2026-10-02T09:00:00+00:00", "value": 100}
        for field in ("oracleDecision", "troughDate", "forwardReturn"):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "ORACLE_FIELD"):
                review.require_ex_ante([{**row, field: 1}], "2026-10-02T09:00:00+00:00")
        with self.assertRaisesRegex(ValueError, "ORACLE_FIELD"):
            review.require_ex_ante([{**row, "feature": "oracleDecision"}],
                                  "2026-10-02T09:00:00+00:00")

    def test_training_maturity_requires_finality_strictly_before_cutoff(self):
        args = ("2026-08-03T20:00:00+00:00", "2026-09-01T20:00:00+00:00",
                "2026-09-01T21:00:00+00:00")
        for cutoff in ("2026-09-01T20:30:00+00:00", "2026-09-01T21:00:00+00:00"):
            with self.subTest(cutoff=cutoff), self.assertRaisesRegex(ValueError, "NONFINAL"):
                review.require_mature_training_label(*args, cutoff)
        review.require_mature_training_label(*args, "2026-09-02T00:00:00+00:00")

    def test_saved_evidence_bridge_and_censoring(self):
        evidence = json.loads((HERE / "evidence.json").read_text())
        self.assertEqual(evidence["newHistoricalEvaluations"], 0)
        for region in evidence["regions"].values():
            for candidate in region["candidates"].values():
                a = candidate["accounting"]
                self.assertAlmostEqual(a["passiveMinusNetCagrPp"],
                                       a["grossMinusNetCostCagrPp"] + a["unattributedNonCostCagrPp"])
        rows = evidence["regions"]["KR"]["candidates"]["C0"]["episodesDepthGe15pct"]["rebound"]
        last = next(x for x in rows if x["troughDate"] == "2026-07-30")
        self.assertIsNone(last["sessionsUntilFullExposure"])
        self.assertIsNone(last["reboundMissedH63"])
        self.assertTrue(last["recoveryWindowCensored"])


if __name__ == "__main__":
    unittest.main()
