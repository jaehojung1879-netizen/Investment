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

    def receipt(self, base, alt, targets, blocks, reasons=None, minimum=1, unmatured=()):
        return c.paired_population_receipt(
            base, alt, targets, intended_by_block=blocks,
            sealed_intended_sha256=c.intended_digest(blocks),
            minimum_complete_blocks=minimum, not_matured_blocks=unmatured,
            missing_reasons=reasons, **S)

    def test_same_member_recurs_across_dates(self):
        blocks = {"D1": ("a",), "D2": ("a",)}
        k = {("D1", "a"): 1, ("D2", "a"): 2}
        r = self.receipt(k, k, {("D1", "a"): .1, ("D2", "a"): .2}, blocks, minimum=2)
        self.assertEqual(r["commonIds"], (("D1", "a"), ("D2", "a")))
        with self.assertRaisesRegex(ValueError, "INVALID_SIGNAL_MEMBERS"):
            self.receipt(k, k, {}, {"D1": ("a", "a")})

    def test_missing_alternative_blocks_only_its_block(self):
        blocks = {"D1": ("a", "b"), "D2": ("a",)}
        base = {("D1", "a"): 1, ("D1", "b"): 2, ("D2", "a"): 3}
        alt = {("D1", "a"): 1, ("D2", "a"): 3}
        tg = {("D1", "a"): .1, ("D1", "b"): .9, ("D2", "a"): .2}
        r = self.receipt(base, alt, tg, blocks)
        self.assertEqual(r["status"], "PARTIAL_BLOCKS_REPORTED")
        self.assertEqual((r["completeBlockCount"], r["blockedBlockCount"]), (1, 1))
        self.assertEqual(r["commonIds"], (("D2", "a"),))
        self.assertEqual(r["blocks"]["D1"]["missing"], {"b": ("ALT_FORECAST_MISSING",)})
        with self.assertRaisesRegex(ValueError, "INSUFFICIENT"):
            c.common_ids(base, alt, tg, intended_by_block=blocks,
                         sealed_intended_sha256=c.intended_digest(blocks),
                         minimum_complete_blocks=2, **S)

    def test_terminal_missing_blocks_whole_block_and_is_counted(self):
        blocks = {"I": ("winner", "terminal")}
        k = {("I", "winner"): 1, ("I", "terminal"): -1}
        r = self.receipt(k, k, {("I", "winner"): .8, ("I", "terminal"): None}, blocks,
                         reasons={("I", "terminal"): ["UNKNOWN_TERMINAL_ECONOMICS", "TRADING_HALT"]})
        self.assertEqual(r["status"], "BLOCKED_INSUFFICIENT_COMPLETE_BLOCKS")
        self.assertEqual(r["commonIds"], ())
        self.assertEqual(r["terminalMissingCount"], 1)
        self.assertEqual(r["missingByReason"], {"TRADING_HALT": 1, "UNKNOWN_TERMINAL_ECONOMICS": 1})

    def test_survivor_only_intended_cohort_fails_sealed_digest(self):
        sealed = c.intended_digest({"I": ("winner", "terminal")})
        survivors = {"I": ("winner",)}
        k = {("I", "winner"): 1}
        with self.assertRaisesRegex(ValueError, "DIGEST_MISMATCH"):
            c.paired_population_receipt(k, k, {("I", "winner"): .8}, intended_by_block=survivors,
                                        sealed_intended_sha256=sealed, minimum_complete_blocks=1, **S)

    def test_unmatured_block_is_calendar_decided_not_missing(self):
        blocks = {"D1": ("a",), "D2": ("a",)}
        k = {("D1", "a"): 1}
        r = self.receipt(k, k, {("D1", "a"): .1}, blocks, unmatured=("D2",))
        self.assertEqual((r["notMaturedBlockCount"], r["missingCount"]), (1, 0))
        self.assertEqual(r["status"], "COMPLETE")
        self.assertEqual(r["evaluatedMemberCoverage"], 1)
        with self.assertRaisesRegex(ValueError, "UNKNOWN_NOT_MATURED"):
            self.receipt(k, k, {}, blocks, unmatured=("D9",))

    def test_post_signal_addition_contradiction_and_params_refused(self):
        b = {"I": ("a",)}
        k = {("I", "a"): 1}
        with self.assertRaisesRegex(ValueError, "INTENDED_SIGNAL"):
            c.common_ids(k, k, {("I", "a"): .1}, intended_by_block=None,
                         sealed_intended_sha256="x", minimum_complete_blocks=1, **S)
        with self.assertRaisesRegex(ValueError, "POST_SIGNAL"):
            self.receipt({("I", "a"): 1, ("I", "s"): 1}, k, {("I", "a"): .1}, b)
        with self.assertRaisesRegex(ValueError, "CONTRADICTORY"):
            self.receipt(k, k, {("I", "a"): .1}, b, reasons={("I", "a"): "SOURCE_OUTAGE"})
        with self.assertRaisesRegex(ValueError, "MINIMUM_COMPLETE"):
            self.receipt(k, k, {("I", "a"): .1}, b, minimum=0)
        with self.assertRaisesRegex(ValueError, "UNKNOWN_OUTCOME_MISSING_REASON"):
            self.receipt(k, k, {}, b, reasons={("I", "a"): "MADE_UP"})

    def test_future_maturity_and_embargo_block_training(self):
        rows = [dict(id="safe", signal=1, entry=2, exit=278),
                dict(id="edge", signal=1, entry=2, exit=279),
                dict(id="future", signal=299, entry=300, exit=552)]
        self.assertEqual(c.training_ids(rows, 300, **S), ("safe",))

    def test_market_rally_is_not_industry_alpha(self):
        self.assertEqual(c.simple_excess(.4, .4, **S), 0)
        self.assertLess(c.simple_excess(.3, .4, **S), 0)

    def test_costs_can_erase_positive_gross_increment(self):
        b = {"I": ("a",)}
        k = {("I", "a"): 1}
        r = self.receipt(k, k, {("I", "a"): .1}, b)
        self.assertLess(c.paired_net_delta(r, ("I", "a"), .10, .11, .001, .02, **S), 0)
        self.assertIsNone(c.paired_net_delta(r, ("I", "a"), .10, .11, None, .02, **S))

    def test_paired_net_requires_approved_receipt_and_member(self):
        b = {"I": ("a", "b")}
        k = {("I", "a"): 1, ("I", "b"): 1}
        ok = self.receipt(k, k, {("I", "a"): .1, ("I", "b"): .1}, b)
        with self.assertRaisesRegex(ValueError, "ID_NOT_IN_APPROVED"):
            c.paired_net_delta(ok, ("I", "zz"), .1, .1, 0, 0, **S)
        forged = dict(ok, commonIds=(("I", "zz"),))
        with self.assertRaisesRegex(ValueError, "APPROVED_RECEIPT"):
            c.paired_net_delta(forged, ("I", "zz"), .1, .1, 0, 0, **S)
        blocked = self.receipt(k, k, {("I", "a"): .1}, b)
        with self.assertRaisesRegex(ValueError, "APPROVED_RECEIPT"):
            c.paired_net_delta(blocked, ("I", "a"), .1, .1, 0, 0, **S)
        with self.assertRaisesRegex(ValueError, "APPROVED_RECEIPT"):
            c.paired_net_delta(None, ("I", "a"), .1, .1, 0, 0, **S)

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
