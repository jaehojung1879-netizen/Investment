"""Only invented, finite structural states and targets; no historical data access."""
import unittest

from pipeline.market_research_reentry_structure import (
    one_rung_reentry, one_rung_path, symbolic_breakout_cells,
    ORIGINAL_RUNG_GRID, STRUCTURAL_HYPOTHESIS, BREAKOUT_HYPOTHESIS,
)


class ReentryStructureTests(unittest.TestCase):
    def test_structural_one_step_and_immediate_exit(self):
        self.assertEqual(one_rung_reentry(.4, 1.0), .7)
        self.assertEqual(one_rung_reentry(.7, 1.0), 1.0)
        self.assertEqual(one_rung_reentry(1.0, .4), .4)
        self.assertEqual(one_rung_reentry(.7, .7), .7)
        self.assertEqual(one_rung_path((.4, 1.0, 1.0, .4, 1.0)),
                         (.4, .7, 1.0, .4, .7))

    def test_no_tunable_or_undefined_rungs(self):
        self.assertEqual(ORIGINAL_RUNG_GRID, (.4, .7, 1.0))
        for prev, desired in ((None, 1.0), (.4, 0.9), (0.0, .7),
                              (True, 1.0), (float("nan"), 1.0)):
            with self.assertRaises(ValueError):
                one_rung_reentry(prev, desired)
        with self.assertRaises(ValueError):
            one_rung_path(())
        with self.assertRaises(ValueError):
            one_rung_path((None,))

    def test_breakout_is_separate_hypothesis_and_works_in_small_cell(self):
        self.assertNotEqual(STRUCTURAL_HYPOTHESIS, BREAKOUT_HYPOTHESIS)
        truth = symbolic_breakout_cells()
        self.assertEqual(len(truth), 24)
        reentry = [x for x in truth if "S2" in x["differences"]]
        self.assertTrue(reentry)
        # This signal cannot accelerate the severe FAST=2 rebound.
        self.assertTrue(all(x["fast"] == 1 and x["breakout"] and
                            (x["slow"] or x["transition"]) for x in reentry))
        self.assertFalse(any(x["fast"] == 2 and "S2" in x["differences"]
                             for x in truth))
        self.assertTrue(all("S1" in x["differences"] for x in truth
                            if x["fast"] == 2))
