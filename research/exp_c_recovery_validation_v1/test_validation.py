"""Invented arrays only; never imports a source loader or reads real outcomes."""
import copy
import csv
import io
import json
import types
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("exp_c_recovery02_engine", HERE / "engine.py")
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)
spec_run = importlib.util.spec_from_file_location("exp_c_recovery02_runner", HERE / "run.py")
runner = importlib.util.module_from_spec(spec_run)
spec_run.loader.exec_module(runner)


def invented(n=2200):
    rng = np.random.default_rng(7202)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    decisions = np.arange(65, n-1, 5)
    states = [[1, int(i % 2 == 0), 0] for i in range(len(decisions))]
    return close, decisions, states


def panel(n=2200):
    close, decisions, states = invented(n)
    rows, audit = e.common_rows(close, decisions, decisions+1, states, [0.7]*len(decisions), set(range(n)))
    return close, rows, audit


class ValidationTests(unittest.TestCase):
    def test_no_future_in_feature_or_cohort(self):
        close, decisions, states = invented()
        d = decisions[0]
        altered = close.copy()
        altered[d+1:] *= 4
        a = e.common_rows(close, [d], [d+1], [states[0]], [0.7], set(range(len(close))))[0][0]
        b = e.common_rows(altered, [d], [d+1], [states[0]], [0.7], set(range(len(close))))[0][0]
        self.assertEqual(a, b)
        self.assertNotIn("y", a)

    def test_execution_and_signed_return(self):
        c, rows, _ = panel()
        r = rows[0]
        self.assertAlmostEqual(r["x"][4], c[r["d"]]/c[r["d"]-63]-1)
        e.attach_labels(c, rows)
        self.assertAlmostEqual(r["y"][63], c[r["e"]+63]/c[r["e"]]-1)

    def test_pending_and_finality_and_missingness(self):
        c, d, s = invented(140)
        c[66] = np.nan
        rows, audit = e.common_rows(c, d, d+1, s, [0.7]*len(d), set(range(139)))
        self.assertEqual(rows, [])
        self.assertIn("TARGET_PATH_MISSING", audit[0]["reasons"])
        self.assertIn("H63_PENDING_OR_NOT_FINAL", audit[-1]["reasons"])
        self.assertEqual(len(audit), len(d))

    def test_next_session_required(self):
        c, d, s = invented()
        with self.assertRaisesRegex(ValueError, "NEXT_SESSION_REQUIRED"):
            e.common_rows(c, [d[0]], [d[0]+2], [s[0]], [0.7], set(range(len(c))))

    def test_zero_volatility_abstains(self):
        rows, audit = e.common_rows(np.ones(200), [65], [66], [[1, 0, 1]], [0.7], set(range(200)))
        self.assertFalse(rows)
        self.assertEqual(audit[0]["reasons"], ["VOL_UNDEFINED"])

    def test_mask_is_common_and_no_rare_event_gate(self):
        c, d, s = invented()
        s[0][1] = None
        rows, audit = e.common_rows(c, d, d+1, s, [0.7]*len(d), set(range(len(c))))
        self.assertNotIn(0, [r["slot"] for r in rows])
        self.assertIn("STATE_MISSING", audit[0]["reasons"])
        self.assertTrue(all(len(r["x"]) == 6 for r in rows))
        self.assertGreater(len(rows), 0)

    def test_embargo_and_strict_finality(self):
        _, rows, _ = panel()
        test = rows[100]
        train = [rows[i] for i in e.train_indices(rows, test)]
        self.assertTrue(train)
        self.assertTrue(all(r["end"]+63 < test["d"] and r["final"] < test["d"] for r in train))
        boundary = copy.deepcopy(train[-1])
        boundary["final"] = test["d"]
        self.assertEqual(e.train_indices([boundary], test), [])

    def test_weekly_rows_are_not_independent_support(self):
        _, rows, _ = panel()
        self.assertLess(e.support(rows), len(rows)/10)
        self.assertFalse(e.preflight_support(rows)["admissible"])

    def test_training_only_standardization(self):
        _, rows, _ = panel()
        y = np.arange(20, dtype=float)
        expected = e.predict(rows[:20], rows[25], y, 6)
        rows[30]["x"] = [1e12]*6
        self.assertEqual(e.predict(rows[:20], rows[25], y, 6), expected)
        self.assertEqual(e.predict(rows[:20], rows[25], y, 0), 9.5)

    def test_constant_columns_regularized_without_failure(self):
        rows = [{"x": [1.0]*6} for _ in range(20)]
        self.assertAlmostEqual(e.predict(rows, rows[0], np.arange(20), 6), 9.5)

    def test_paired_oos_training_folds(self):
        c, rows, _ = panel()
        scored, _ = e.walk_forward(e.attach_labels(c, rows))
        self.assertTrue(scored)
        self.assertTrue(all(len(r["scores"][63]["loss"]) == 3 for r in scored))
        self.assertTrue(all(r["latest_train_end"]+63 < r["d"] for r in scored))
        self.assertTrue(all(r["train_support"] >= e.MIN_TRAIN_SUPPORT for r in scored))

    def test_uncertainty_refuses_thin_blocks(self):
        c, rows, _ = panel()
        scored, _ = e.walk_forward(e.attach_labels(c, rows))
        result = e.paired_uncertainty(scored)
        self.assertIsNone(result["p"])
        self.assertIsNone(result["ci95"])
        self.assertIsNotNone(result["delta"])

    def test_fixed_bootstrap_reproducible_with_calendar_gaps(self):
        rng = np.random.default_rng(22)
        scored = [{"d": i*126, "scores": {63: {"loss": [1, 1.01+float(rng.normal(0, .1)), 1]}}}
                  for i in range(65) if i % 3 != 1]
        a = e.paired_uncertainty(scored)
        self.assertEqual(a, e.paired_uncertainty(scored))
        self.assertEqual(a["blocks"], len(scored))
        self.assertLessEqual(a["ci95"][0], a["ci95"][1])
        self.assertTrue(0 < a["p"] <= 1)

    def test_single_conjunction_does_not_promote_one_country(self):
        good = {"verdict": "POSITIVE_REGION_COMPONENT", "primary": {"p": .02}}
        bad = {"verdict": "NO_EVIDENCE"}
        self.assertEqual(e.joint_verdict({"KR": good, "US": bad})["verdict"], "NO_EVIDENCE")
        self.assertEqual(e.joint_verdict({"KR": good, "US": {"verdict": "POWER_BLOCKED"}})["verdict"], "POWER_BLOCKED")
        self.assertEqual(e.joint_verdict({"KR": good, "US": good})["primary_p"], .02)

    def test_owner_identity_cannot_be_supplied_in_body(self):
        with self.assertRaisesRegex(ValueError, "OWNER_IDENTITY_REQUIRED"):
            runner.authorization("frozen", {"user": {"login": "not-owner"}, "body": "{}"}, "source")

    def test_handoff_is_not_execution_token(self):
        with self.assertRaises(ValueError):
            runner.authorization("frozen", {"user": {"login": runner.OWNER}, "body": "{}"}, "source")

    def test_immutable_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"receipt.json"
            runner.persist(path, {"status": "SYNTHETIC"})
            with self.assertRaises(FileExistsError):
                runner.persist(path, {})

    def test_exact_source_tamper_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/"code.py").write_text("# invented\n")
            (root/"raw.json").write_text("{}")
            (root/"SOURCES.json").write_text(json.dumps({"repository_pins": {"code.py": runner.sha(root/"code.py")},
                                                       "us_pins": {"raw.json": runner.sha(root/"raw.json")}}))
            with patch.object(runner, "HERE", root), patch.object(runner, "ROOT", root):
                runner.source_gate(root)
                (root/"raw.json").write_text('{"revision":true}')
                with self.assertRaisesRegex(ValueError, "US_FROZEN_SOURCE_MISSING_OR_CHANGED"):
                    runner.source_gate(root)

    def test_approval_exact_hash_and_head(self):
        body = {"study": runner.STUDY, "freeze_sha256": "frozen", "source_manifest_sha256": "source",
                "closure_exception": "C.7_AND_STOP_LIST_SINGLE_COMPARISON_ONLY", "outcome_exposed": True,
                "one_shot": True, "source_rights_accepted": True, "persistence_ready": True,
                "action": "AUTHORIZE_EXACT_HASH_HISTORICAL_EXECUTION", "code_commit": "head"}
        comment = {"user": {"login": runner.OWNER}, "body": json.dumps(body)}
        with patch.object(runner, "git", side_effect=["head", ""]):
            self.assertEqual(runner.authorization("frozen", comment, "source"), body)
        with self.assertRaisesRegex(ValueError, "EXACT_OWNER_AUTHORIZATION_MISMATCH"):
            runner.authorization("changed", comment, "source")
        with patch.object(runner, "git", return_value="other-head"):
            with self.assertRaisesRegex(ValueError, "OWNER_EXACT_HEAD_MISMATCH"):
                runner.authorization("frozen", comment, "source")

    def test_source_adapter_calls_sealed_calendar_and_states(self):
        # Synthetic source plumbing only; no real sealed module is evaluated.
        import pandas as pd
        calls = []
        dates = pd.bdate_range("2000-01-03", periods=220)
        c, _, _ = invented(220)
        csv_data = "date,value\n" + "".join(f"{d.date()},{v}\n" for d, v in zip(dates, c))
        def states(*args):
            calls.append("states")
            return pd.DataFrame({"fast": 1, "slow": 0, "transition": 1}, index=dates)
        def schedule(*args):
            calls.append("schedule")
            return pd.DataFrame({"decisionDate": dates[65:-1:5], "executionDate": dates[66::5]})
        def targets(st, sched, name):
            self.assertEqual(name, "C0")
            return pd.DataFrame({"target": [0.7]*len(sched)})
        def observations(rows):
            return pd.Series([v for _, v in rows], index=pd.to_datetime([d for d, _ in rows]))
        modules = {"pipeline": types.ModuleType("pipeline"),
            "pipeline.kr_market_risk_anatomy": types.SimpleNamespace(obs_series=observations),
            "pipeline.kr_market_risk_source_parse": types.SimpleNamespace(read_normalized=lambda b: [
                (r["date"], float(r["value"])) for r in csv.DictReader(io.StringIO(b.decode()))]),
            "pipeline.kr_market_risk_model": types.SimpleNamespace(layer_states=states, decision_schedule=schedule,
                candidate_targets=targets, EVALUATION_START="2007-01-01"),
            "pipeline.rp1_c1_us_exposure": types.SimpleNamespace(layer_states=states, decision_schedule=schedule,
                market_sessions=lambda *a: dates, GRID_START="1990-01-01", EVALUATION_START="1993-02-01")}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for sid in ("FDR_KS200", "FRED_DGS10", "FRED_DGS3MO", "FRED_VIXCLS"):
                path = root/"data/kr-market-risk-anatomy-v1/sources"/sid/"normalized.csv"
                path.parent.mkdir(parents=True)
                path.write_text(csv_data)
            (root/"YAHOO_GSPC").mkdir()
            (root/"YAHOO_GSPC/normalized.csv").write_text(csv_data)
            with patch.dict(sys.modules, modules):
                panels = runner.prepare_sources(root, root, {"analysis_end": "2026-09-17"})
        self.assertEqual(calls, ["states", "schedule", "states", "schedule"])
        self.assertEqual(set(panels), {"KR", "US"})
        self.assertEqual(panels["KR"]["rows"], panels["US"]["rows"])
        self.assertTrue(all("y" not in r for r in panels["KR"]["rows"]))

    def test_execute_without_approval_never_reaches_network_or_source(self):
        with patch.object(sys, "argv", ["run.py", "--execute"]), \
             patch.object(runner, "freeze_identity", return_value="SYNTHETIC"), \
             patch.object(runner, "api", side_effect=AssertionError("network call")), \
             patch.object(runner, "prepare_sources", side_effect=AssertionError("value read")):
            self.assertEqual(runner.main(), 2)

    def test_default_has_no_value_loader(self):
        with patch.object(sys, "argv", ["run.py"]), patch.object(runner, "freeze_identity", return_value="SYNTHETIC"), \
             patch.object(runner, "prepare_sources", side_effect=AssertionError("value read")):
            self.assertEqual(runner.main(), 0)


if __name__ == "__main__":
    unittest.main()
