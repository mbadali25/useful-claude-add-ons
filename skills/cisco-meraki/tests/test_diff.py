import unittest

import context  # noqa: F401

from helpers import DEFAULT_RULE, rule
from meraki_diff import (
    diff_rules,
    is_default_l3_rule,
    redact_secrets,
    render_diff,
    rule_key,
    strip_default_rule,
)


class TestDefaultRule(unittest.TestCase):
    def test_recognizes_merakis_implicit_default(self):
        self.assertTrue(is_default_l3_rule(DEFAULT_RULE))

    def test_real_allow_any_rule_with_a_comment_is_not_the_default(self):
        self.assertFalse(is_default_l3_rule(rule("allow", "Any",
                                                 comment="permit egress")))

    def test_deny_rule_is_not_the_default(self):
        self.assertFalse(is_default_l3_rule(rule("deny", "Any",
                                                 comment="Default rule")))

    def test_strip_removes_only_a_trailing_default(self):
        rules = [rule("deny", "10.0.0.0/8"), DEFAULT_RULE]
        self.assertEqual(strip_default_rule(rules), [rule("deny", "10.0.0.0/8")])

    def test_strip_is_a_noop_without_a_default(self):
        rules = [rule("deny", "10.0.0.0/8")]
        self.assertEqual(strip_default_rule(rules), rules)

    def test_strip_leaves_a_non_trailing_default_alone(self):
        rules = [DEFAULT_RULE, rule("deny", "10.0.0.0/8")]
        self.assertEqual(len(strip_default_rule(rules)), 2)

    def test_strip_does_not_mutate_the_input(self):
        rules = [rule("deny", "10.0.0.0/8"), DEFAULT_RULE]
        strip_default_rule(rules)
        self.assertEqual(len(rules), 2)


class TestDiffRules(unittest.TestCase):
    def test_identical_lists_produce_no_diff(self):
        rules = [rule("deny", "10.0.0.0/8"), rule("allow", "192.168.0.0/16")]
        self.assertEqual(diff_rules(rules, list(rules)), [])

    def test_detects_an_addition_with_position(self):
        current = [rule("deny", "10.0.0.0/8")]
        proposed = current + [rule("allow", "192.168.0.0/16")]
        lines = diff_rules(current, proposed)
        self.assertEqual([(op, pos) for op, pos, _ in lines], [("added", 2)])

    def test_detects_a_removal_with_position(self):
        current = [rule("deny", "10.0.0.0/8"), rule("allow", "192.168.0.0/16")]
        proposed = [rule("deny", "10.0.0.0/8")]
        lines = diff_rules(current, proposed)
        self.assertEqual([(op, pos) for op, pos, _ in lines], [("removed", 2)])

    def test_reorder_with_identical_membership_is_a_change(self):
        """The critical case: a set-based diff would call this 'no change',
        but moving a deny above a permit changes behavior."""
        allow = rule("allow", "10.0.0.0/8", comment="permit")
        deny = rule("deny", "10.0.0.0/8", comment="block")
        lines = diff_rules([allow, deny], [deny, allow])
        self.assertNotEqual(lines, [])
        self.assertTrue(all(op == "moved" for op, _, _ in lines))

    def test_field_edit_in_place_is_reported_as_changed(self):
        current = [rule("allow", "10.0.0.0/8")]
        proposed = [rule("deny", "10.0.0.0/8")]
        lines = diff_rules(current, proposed)
        self.assertEqual([op for op, _, _ in lines], ["changed"])

    def test_empty_to_populated(self):
        lines = diff_rules([], [rule("deny", "10.0.0.0/8")])
        self.assertEqual([op for op, _, _ in lines], ["added"])

    def test_rule_key_is_order_independent_over_dict_keys(self):
        a = {"policy": "deny", "destCidr": "Any"}
        b = {"destCidr": "Any", "policy": "deny"}
        self.assertEqual(rule_key(a), rule_key(b))

    def test_reorder_co_occurring_with_addition_still_reports_the_move(self):
        """Regression: a swap must remain visible even when an unrelated
        rule is added in the same call. The old implementation only
        detected 'moved' from an early-return branch guarded on identical
        set membership and length, so this exact case -- swap plus an
        addition -- reported only the addition and hid the swap entirely."""
        allow = rule("allow", "10.0.0.0/8", comment="permit")
        deny = rule("deny", "10.0.0.0/8", comment="block")
        new_rule = rule("allow", "8.8.8.8/32", comment="new")
        current = [allow, deny]
        proposed = [deny, allow, new_rule]
        lines = diff_rules(current, proposed)
        ops = [op for op, _, _ in lines]
        self.assertIn("moved", ops)
        self.assertIn("added", ops)

    def test_reorder_co_occurring_with_removal_reports_both(self):
        a = rule("allow", "1.1.1.1/32", comment="a")
        b = rule("deny", "2.2.2.2/32", comment="b")
        c = rule("allow", "3.3.3.3/32", comment="c")
        current = [a, b, c]
        proposed = [b, a]
        lines = diff_rules(current, proposed)
        ops = [op for op, _, _ in lines]
        self.assertIn("moved", ops)
        self.assertIn("removed", ops)

    def test_in_place_edit_and_separate_insertion_are_independent(self):
        edited = rule("allow", "10.0.0.0/8", comment="edit-me")
        kept = rule("deny", "192.168.0.0/16", comment="keep")
        current = [edited, kept]
        proposed = [
            rule("deny", "10.0.0.0/8", comment="edit-me"),
            kept,
            rule("allow", "8.8.8.8/32", comment="new"),
        ]
        lines = diff_rules(current, proposed)
        changed = [(op, pos) for op, pos, _ in lines if op == "changed"]
        added = [(op, pos) for op, pos, _ in lines if op == "added"]
        self.assertEqual(changed, [("changed", 1)])
        self.assertEqual(added, [("added", 3)])

    def test_middle_removal_shifts_tail_without_spurious_changes(self):
        r1 = rule("allow", "1.1.1.1/32", comment="one")
        r2 = rule("deny", "2.2.2.2/32", comment="two")
        r3 = rule("allow", "3.3.3.3/32", comment="three")
        lines = diff_rules([r1, r2, r3], [r1, r3])
        self.assertEqual([(op, pos) for op, pos, _ in lines], [("removed", 2)])

    def test_duplicate_rules_removal_is_not_mistaken_for_a_move(self):
        dup = rule("deny", "10.0.0.0/8", comment="dup")
        lines = diff_rules([dup, dup], [dup])
        ops = [op for op, _, _ in lines]
        self.assertEqual(ops, ["removed"])
        self.assertNotIn("moved", ops)

    def test_known_limitation_swap_with_edited_rule_loses_move_label(self):
        """Documents an accepted limitation, not desired behavior.

        Move detection links a removal to an addition by exact content
        equality, so editing one of two swapped rules breaks the link: the
        edit is reported with correct positions and content, but the swap
        loses its 'moved' label and the unedited counterpart is not
        reported at all. Fixing it needs fuzzy matching of an edited rule
        to its pre-edit self, which is deliberately not implemented.

        If a future change makes this test fail, that is likely an
        IMPROVEMENT -- update diff_rules' docstring and this test together
        rather than reverting the change.
        """
        allow       = rule("allow", "10.0.0.0/8", comment="permit")
        deny        = rule("deny",  "10.0.0.0/8", comment="block")
        deny_edited = rule("deny",  "10.0.0.0/8", comment="block-edited")

        lines = diff_rules([allow, deny], [deny_edited, allow])

        # The diff is non-empty (so the confirm gate a human sees is never
        # silently blank), but there is no 'moved' op.
        self.assertNotEqual(lines, [])
        ops = [op for op, _, _ in lines]
        self.assertNotIn("moved", ops)

        # The observed output: the edited rule appears as an addition,
        # the original appears as a removal. The unedited 'allow' rule
        # (which changed position but not content) does not appear.
        self.assertEqual(len(lines), 2)
        self.assertEqual([(op, pos) for op, pos, _ in lines], [("added", 1), ("removed", 2)])


class TestRenderDiff(unittest.TestCase):
    def test_renders_signed_prefixes_and_positions(self):
        lines = [
            ("added", 2, rule("allow", "192.168.0.0/16")),
            ("removed", 3, rule("deny", "10.0.0.0/8")),
            ("moved", 1, rule("deny", "172.16.0.0/12")),
            ("changed", 4, rule("allow", "8.8.8.8/32")),
        ]
        out = render_diff(lines)
        self.assertIn("+ [2]", out)
        self.assertIn("- [3]", out)
        self.assertIn("~ [1]", out)
        self.assertIn("~ [4]", out)

    def test_empty_diff_says_so_explicitly(self):
        self.assertIn("no change", render_diff([]).lower())

    def test_rendered_diff_redacts_secrets(self):
        lines = [("changed", 1, {"name": "vpn", "psk": "hunter2"})]
        out = render_diff(lines)
        self.assertNotIn("hunter2", out)


class TestRedactSecrets(unittest.TestCase):
    def test_redacts_known_secret_keys(self):
        out = redact_secrets({"name": "hq", "psk": "hunter2"})
        self.assertEqual(out["name"], "hq")
        self.assertNotIn("hunter2", str(out))

    def test_is_case_insensitive_on_key_names(self):
        out = redact_secrets({"sharedSecret": "s1", "PSK": "s2"})
        self.assertNotIn("s1", str(out))
        self.assertNotIn("s2", str(out))

    def test_recurses_into_lists_and_dicts(self):
        out = redact_secrets({"peers": [{"name": "a", "psk": "deep-secret"}]})
        self.assertNotIn("deep-secret", str(out))

    def test_does_not_mutate_the_original(self):
        original = {"psk": "hunter2"}
        redact_secrets(original)
        self.assertEqual(original["psk"], "hunter2")


if __name__ == "__main__":
    unittest.main()
