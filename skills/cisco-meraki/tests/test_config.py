import json
import os
import shutil
import tempfile
import unittest

import context  # noqa: F401

from helpers import DEFAULT_RULE, http_with, ok, rule
from meraki_http import MerakiError
from meraki_config import (
    ConfigTool,
    HardBlocked,
    check_hard_block,
    extract_rules,
)

FW_PATH = "/networks/N1/appliance/firewall/l3FirewallRules"


class TestHardBlocks(unittest.TestCase):
    def test_blocks_network_deletion(self):
        with self.assertRaises(HardBlocked):
            check_hard_block("DELETE", "/networks/N1")

    def test_blocks_org_deletion(self):
        with self.assertRaises(HardBlocked):
            check_hard_block("DELETE", "/organizations/111")

    def test_blocks_device_removal(self):
        with self.assertRaises(HardBlocked):
            check_hard_block("POST", "/networks/N1/devices/remove")

    def test_blocks_inventory_release(self):
        with self.assertRaises(HardBlocked):
            check_hard_block("POST", "/organizations/111/inventory/release")

    def test_blocks_admin_revocation(self):
        with self.assertRaises(HardBlocked):
            check_hard_block("DELETE", "/organizations/111/admins/A1")

    def test_blocks_api_key_operations(self):
        with self.assertRaises(HardBlocked):
            check_hard_block("DELETE",
                             "/administered/identities/me/api/keys/abc/revoke")

    def test_refusal_explains_why_and_points_at_the_ui(self):
        with self.assertRaises(HardBlocked) as ctx:
            check_hard_block("DELETE", "/networks/N1")
        message = str(ctx.exception).lower()
        self.assertIn("dashboard", message)

    def test_allows_ordinary_firewall_write(self):
        check_hard_block("PUT", FW_PATH)  # must not raise

    def test_allows_vlan_write(self):
        check_hard_block("PUT", "/networks/N1/appliance/vlans/10")


class TestExtractRules(unittest.TestCase):
    def test_unwraps_a_rules_envelope(self):
        self.assertEqual(extract_rules({"rules": [rule("deny", "Any")]}),
                         [rule("deny", "Any")])

    def test_passes_a_bare_list_through(self):
        self.assertEqual(extract_rules([rule("deny", "Any")]),
                         [rule("deny", "Any")])

    def test_wraps_a_scalar_object_as_a_single_item(self):
        self.assertEqual(extract_rules({"name": "hq"}), [{"name": "hq"}])


class TestSnapshot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_writes_a_timestamped_file_and_returns_its_path(self):
        http, _ = http_with([ok({"rules": [rule("deny", "10.0.0.0/8"),
                                           DEFAULT_RULE]})])
        tool = ConfigTool(http, snapshot_dir=self.tmp, now=lambda: "20260729-120000")

        path = tool.snapshot(FW_PATH)

        self.assertTrue(os.path.exists(path))
        self.assertIn("20260729-120000", path)
        with open(path, encoding="utf-8") as fh:
            saved = json.load(fh)
        self.assertEqual(saved["path"], FW_PATH)
        self.assertEqual(saved["payload"]["rules"][1], DEFAULT_RULE)

    def test_snapshot_preserves_secrets_verbatim(self):
        http, _ = http_with([ok({"psk": "hunter2"})])
        tool = ConfigTool(http, snapshot_dir=self.tmp, now=lambda: "t")
        path = tool.snapshot("/networks/N1/appliance/vpn/siteToSiteVpn")
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["payload"]["psk"], "hunter2")


class TestApply(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _tool(self, responses):
        http, calls = http_with(responses)
        return ConfigTool(http, snapshot_dir=self.tmp,
                          now=lambda: "20260729-120000"), calls

    def test_snapshots_then_puts_on_confirmation(self):
        current = {"rules": [rule("deny", "10.0.0.0/8"), DEFAULT_RULE]}
        proposed = {"rules": [rule("deny", "10.0.0.0/8"),
                              rule("allow", "192.168.0.0/16")]}
        tool, calls = self._tool([ok(current), ok(proposed)])

        tool.apply(FW_PATH, proposed, confirm=lambda text: True)

        self.assertEqual(calls[0][0], "GET")
        self.assertEqual(calls[1][0], "PUT")
        self.assertTrue(os.listdir(self.tmp))

    def test_declining_confirmation_performs_no_write(self):
        current = {"rules": [rule("deny", "10.0.0.0/8"), DEFAULT_RULE]}
        proposed = {"rules": [rule("allow", "0.0.0.0/0")]}
        tool, calls = self._tool([ok(current)])

        with self.assertRaises(MerakiError):
            tool.apply(FW_PATH, proposed, confirm=lambda text: False)

        self.assertEqual([c[0] for c in calls], ["GET"])

    def test_confirmation_receives_the_rendered_diff_not_a_count(self):
        current = {"rules": [rule("deny", "10.0.0.0/8"), DEFAULT_RULE]}
        proposed = {"rules": [rule("deny", "10.0.0.0/8"),
                              rule("allow", "192.168.0.0/16")]}
        tool, _ = self._tool([ok(current), ok(proposed)])
        seen = {}

        tool.apply(FW_PATH, proposed,
                   confirm=lambda text: seen.setdefault("text", text) or True)

        self.assertIn("+ [2]", seen["text"])
        self.assertIn("192.168.0.0/16", seen["text"])

    def test_no_op_change_is_refused_before_any_write(self):
        current = {"rules": [rule("deny", "10.0.0.0/8"), DEFAULT_RULE]}
        proposed = {"rules": [rule("deny", "10.0.0.0/8")]}
        tool, calls = self._tool([ok(current)])

        with self.assertRaises(MerakiError) as ctx:
            tool.apply(FW_PATH, proposed, confirm=lambda text: True)

        self.assertIn("no change", str(ctx.exception).lower())
        self.assertEqual([c[0] for c in calls], ["GET"])

    def test_default_rule_is_never_sent_in_the_put_body(self):
        current = {"rules": [rule("deny", "10.0.0.0/8"), DEFAULT_RULE]}
        proposed = {"rules": [rule("deny", "10.0.0.0/8"),
                              rule("allow", "192.168.0.0/16"), DEFAULT_RULE]}
        tool, calls = self._tool([ok(current), ok({})])

        tool.apply(FW_PATH, proposed, confirm=lambda text: True)

        sent = json.loads(calls[1][2].decode())
        self.assertEqual(len(sent["rules"]), 2)
        self.assertNotIn("Default rule",
                         [r.get("comment") for r in sent["rules"]])

    def test_hard_blocked_path_never_reaches_the_network(self):
        tool, calls = self._tool([])
        with self.assertRaises(HardBlocked):
            tool.apply("/administered/identities/me/api/keys/abc123", {},
                       confirm=lambda text: True)
        self.assertEqual(calls, [])

    def test_network_attribute_update_is_not_hard_blocked(self):
        """PUT /networks/{id} edits attributes (name, timezone, tags) -- a
        reversible change a snapshot can restore, so it is deliberately NOT
        hard-blocked. Only DELETE /networks/{id} is, because destroying a
        network cannot be undone from a snapshot.
        """
        # PUT should not raise -- not raising is the expected behavior
        check_hard_block("PUT", "/networks/N1")

        # DELETE should raise HardBlocked
        with self.assertRaises(HardBlocked):
            check_hard_block("DELETE", "/networks/N1")

    def test_reorder_is_applied_because_it_is_a_real_change(self):
        allow = rule("allow", "10.0.0.0/8", comment="permit")
        deny = rule("deny", "10.0.0.0/8", comment="block")
        tool, calls = self._tool([ok({"rules": [allow, deny, DEFAULT_RULE]}),
                                  ok({})])

        tool.apply(FW_PATH, {"rules": [deny, allow]},
                   confirm=lambda text: True)

        self.assertEqual(calls[1][0], "PUT")


class TestRollback(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_re_puts_the_snapshot_payload(self):
        snap = os.path.join(self.tmp, "snap.json")
        with open(snap, "w", encoding="utf-8") as fh:
            json.dump({"path": FW_PATH,
                       "payload": {"rules": [rule("deny", "10.0.0.0/8"),
                                             DEFAULT_RULE]}}, fh)
        http, calls = http_with([ok({"rules": [rule("allow", "0.0.0.0/0"),
                                               DEFAULT_RULE]}), ok({})])
        tool = ConfigTool(http, snapshot_dir=self.tmp, now=lambda: "t")

        tool.rollback(snap, confirm=lambda text: True)

        self.assertEqual(calls[-1][0], "PUT")
        sent = json.loads(calls[-1][2].decode())
        self.assertEqual(len(sent["rules"]), 1)

    def test_missing_snapshot_file_raises(self):
        http, _ = http_with([])
        tool = ConfigTool(http, snapshot_dir=self.tmp, now=lambda: "t")
        with self.assertRaises(MerakiError):
            tool.rollback(os.path.join(self.tmp, "nope.json"),
                          confirm=lambda text: True)


if __name__ == "__main__":
    unittest.main()
