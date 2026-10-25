"""Invented examples only. Importing this suite cannot access a historical runner."""
import copy
import unittest

from research.industry_alpha_next_v1 import contracts as c

S = {"scope": "SYNTHETIC_FIXTURE"}


class IndustryContractTests(unittest.TestCase):
    def assignment(self):
        return dict(security_id="SYN:A", industry_id="SYN:I", taxonomy_version="SYN:1",
                    source_sha256="a" * 64, evidence_class="PIT_CONFIRMED",
                    published_at="2030-01-01T00:00:00+00:00",
                    valid_from="2029-12-01T00:00:00+00:00", valid_to=None)

    def test_release_is_strictly_before_signal(self):
        r = self.assignment()
        self.assertFalse(c.visible_assignment(r, r["published_at"], **S))
        self.assertTrue(c.visible_assignment(r, "2030-01-02T00:00:00+00:00", **S))

    def test_future_effective_date_is_not_current_membership(self):
        r = self.assignment(); r["valid_from"] = "2031-01-01T00:00:00+00:00"
        self.assertFalse(c.visible_assignment(r, "2030-01-02T00:00:00+00:00", **S))

    def test_interval_end_is_exclusive(self):
        r = self.assignment(); r["valid_to"] = "2030-01-02T00:00:00+00:00"
        self.assertFalse(c.visible_assignment(r, r["valid_to"], **S))

    def test_reconstruction_never_becomes_strict_pit(self):
        for state in ("CURRENT_ONLY", "RECONSTRUCTED_STABLE_NO_CHANGE_EVENT", "UNKNOWN"):
            r = self.assignment(); r["evidence_class"] = state
            self.assertFalse(c.visible_assignment(r, "2030-01-02T00:00:00+00:00", **S))

    def test_identity_and_digest_and_timezone_required(self):
        for key, value in (("security_id", None), ("taxonomy_version", ""),
                           ("source_sha256", "z" * 64), ("published_at", "2030-01-01")):
            r = self.assignment(); r[key] = value
            self.assertFalse(c.visible_assignment(r, "2030-01-02T00:00:00+00:00", **S))

    def test_missing_terminal_is_not_survivor_renormalization(self):
        self.assertIsNone(c.frozen_return({"SYN:A": .8, "SYN:B": .2}, {"SYN:A": .3}, **S))

    def test_observed_zero_and_total_loss_are_real_values(self):
        self.assertAlmostEqual(c.frozen_return({"SYN:A": .8, "SYN:B": .2},
                                              {"SYN:A": 0, "SYN:B": -1}, **S), -.2)

    def test_nonfinite_or_boolean_return_is_not_zero(self):
        for v in (float("nan"), float("inf"), False, -1.1):
            self.assertIsNone(c.frozen_return({"SYN:A": 1}, {"SYN:A": v}, **S))

    def test_frozen_cap_cohort_does_not_reweight_by_future_winners(self):
        self.assertAlmostEqual(c.frozen_return({"SYN:A": .9, "SYN:B": .1},
                                              {"SYN:A": 0, "SYN:B": 1}, **S), .1)

    def test_mega_cap_removal_rechecks_depth(self):
        w = {f"SYN:{i}": 1/5 for i in range(5)}
        self.assertIsNone(c.excluding(w, {"SYN:0"}, **S))
        w["SYN:5"] = .2
        self.assertEqual(len(c.excluding(w, {"SYN:0"}, **S)), 5)
        self.assertAlmostEqual(sum(c.excluding(w, {"SYN:0"}, **S).values()), 1)

    def test_paired_population_cannot_reward_missing_alternative(self):
        frozen = {"SYN:DATE1": ("a", "b", "c")}
        args = ({"a": 1, "b": 2, "c": 3},
                {"a": 1, "c": None}, {"a": .1, "b": .9, "c": .2})
        receipt = c.paired_population_receipt(*args, intended_by_block=frozen, **S)
        self.assertEqual(receipt["status"], "BLOCKED_INCOMPLETE_INTENDED_POPULATION")
        self.assertEqual(receipt["missingCount"], 2)
        self.assertEqual(receipt["commonIds"], ())
        self.assertFalse(receipt["inferentialComparisonAllowed"])
        with self.assertRaisesRegex(ValueError, "BLOCKED_INCOMPLETE"):
            c.common_ids(*args, intended_by_block=frozen, **S)

    def test_terminal_missing_does_not_promote_survivor_only_winners(self):
        cohort = {"SYN:INDUSTRY": ("winner", "terminal")}
        receipt = c.paired_population_receipt(
            {"winner": 1, "terminal": -1}, {"winner": 2, "terminal": -1},
            {"winner": .8, "terminal": None}, intended_by_block=cohort,
            missing_reasons={"terminal": "UNKNOWN_TERMINAL_ECONOMICS"}, **S)
        self.assertEqual(receipt["blockedBlockCount"], 1)
        self.assertEqual(receipt["coverage"], 0)
        self.assertEqual(receipt["blocks"]["SYN:INDUSTRY"]["missing"]["terminal"],
                         "UNKNOWN_TERMINAL_ECONOMICS")

    def test_missing_outcome_reason_and_intended_denominator_preserved(self):
        receipt = c.paired_population_receipt(
            {"a": 1, "b": 1}, {"a": 1, "b": 1}, {"a": .2},
            intended_by_block={"SYN:ONE": ("a", "b")},
            missing_reasons={"b": "SOURCE_OUTAGE"}, **S)
        self.assertEqual(receipt["intendedCount"], 2)
        self.assertEqual(receipt["missingCount"], 1)
        self.assertEqual(receipt["commonIds"], ())
        self.assertEqual(receipt["blocks"]["SYN:ONE"]["missing"], {"b": "SOURCE_OUTAGE"})

    def test_complete_population_allows_exact_frozen_ids(self):
        a, b, targets = {"a": 1, "b": 2}, {"a": 2, "b": 3}, {"a": 0, "b": -.5}
        frozen = {"SYN:ONE": ("b", "a")}
        self.assertEqual(c.common_ids(a, b, targets, intended_by_block=frozen, **S),
                         ("a", "b"))
        r = c.paired_population_receipt(a, b, targets, intended_by_block=frozen, **S)
        self.assertEqual(r["coverage"], 1)
        self.assertTrue(r["inferentialComparisonAllowed"])

    def test_post_signal_addition_and_unregistered_denominator_refused(self):
        with self.assertRaisesRegex(ValueError, "INTENDED_SIGNAL"):
            c.common_ids({"a": 1}, {"a": 1}, {"a": .1}, **S)
        with self.assertRaisesRegex(ValueError, "POST_SIGNAL"):
            c.common_ids({"a": 1, "survivor": 1}, {"a": 1}, {"a": .1},
                         intended_by_block={"SYN:ONE": ("a",)}, **S)
        with self.assertRaisesRegex(ValueError, "CONTRADICTORY"):
            c.paired_population_receipt(
                {"a": 1}, {"a": 1}, {"a": .1},
                intended_by_block={"SYN:ONE": ("a",)},
                missing_reasons={"a": "SOURCE_OUTAGE"}, **S)

    def test_future_maturity_and_embargo_block_training(self):
        rows = [dict(id="safe", signal=1, entry=2, exit=278),
                dict(id="edge", signal=1, entry=2, exit=279),
                dict(id="future", signal=299, entry=300, exit=552)]
        self.assertEqual(c.training_ids(rows, 300, **S), ("safe",))

    def test_market_rally_is_not_industry_alpha(self):
        self.assertEqual(c.simple_excess(.4, .4, **S), 0)
        self.assertLess(c.simple_excess(.3, .4, **S), 0)

    def test_costs_can_erase_positive_gross_increment(self):
        self.assertLess(c.paired_net_delta(.10, .11, .001, .02, **S), 0)
        self.assertIsNone(c.paired_net_delta(.10, .11, None, .02, **S))

    def test_leaders_and_laggards_must_be_disjoint_nonempty(self):
        self.assertIsNone(c.leader_gap({"a": .2}, {"a"}, **S))
        self.assertAlmostEqual(c.leader_gap({"a": .3, "b": .1}, {"a"}, **S), .2)

    def test_no_input_mutation(self):
        w = {f"SYN:{i}": 1 for i in range(6)}; before = copy.deepcopy(w)
        c.excluding(w, {"SYN:0"}, **S)
        self.assertEqual(w, before)

    def test_real_scope_is_refused(self):
        with self.assertRaisesRegex(ValueError, "SYNTHETIC_ONLY"):
            c.frozen_return({"005930.KS": 1}, {"005930.KS": .1}, scope="REAL")


if __name__ == "__main__":
    unittest.main()
