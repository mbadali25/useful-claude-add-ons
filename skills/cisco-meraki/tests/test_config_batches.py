import json
import shutil
import tempfile
import unittest

import context  # noqa: F401  # pylint: disable=unused-import

from helpers import http_with, ok
from meraki_diff import redact_secrets
from meraki_http import MerakiError
from meraki_config import (
    MAX_BATCH_ACTIONS,
    MAX_PENDING_BATCHES,
    ConfigTool,
    HardBlocked,
)


def action(resource="/networks/N1/appliance/vlans/10", operation="update"):
    return {"resource": resource, "operation": operation,
            "body": {"name": "voice"}}


class TestBatchStage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _tool(self, responses):
        http, calls = http_with(responses)
        return ConfigTool(http, snapshot_dir=self.tmp, now=lambda: "t"), calls

    def test_stages_unconfirmed_so_meraki_validates_first(self):
        tool, calls = self._tool([
            ok([{"id": "111"}]),
            ok([]),
            ok({"id": "B1", "status": {"completed": False, "failed": False}}),
        ])

        tool.batch_stage([action()])

        method, url, body = calls[-1]
        self.assertEqual(method, "POST")
        self.assertIn("/organizations/111/actionBatches", url)
        self.assertIs(json.loads(body.decode())["confirmed"], False)

    def test_rejects_more_than_the_action_cap(self):
        tool, _calls = self._tool([ok([{"id": "111"}]), ok([])])
        too_many = [action()] * (MAX_BATCH_ACTIONS + 1)
        with self.assertRaises(MerakiError) as ctx:
            tool.batch_stage(too_many)
        self.assertIn(str(MAX_BATCH_ACTIONS), str(ctx.exception))

    def test_rejects_an_empty_action_list(self):
        tool, _ = self._tool([ok([{"id": "111"}]), ok([])])
        with self.assertRaises(MerakiError):
            tool.batch_stage([])

    def test_refuses_when_pending_batches_are_at_the_cap(self):
        pending = [{"id": f"B{i}", "status": {"completed": False,
                                              "failed": False}}
                   for i in range(MAX_PENDING_BATCHES)]
        tool, calls = self._tool([ok([{"id": "111"}]), ok(pending)])
        with self.assertRaises(MerakiError) as ctx:
            tool.batch_stage([action()])
        self.assertIn(str(MAX_PENDING_BATCHES), str(ctx.exception))
        self.assertEqual(len(calls), 2)  # no POST attempted

    def test_hard_blocked_resource_is_rejected_before_staging(self):
        tool, calls = self._tool([ok([{"id": "111"}]), ok([])])
        bad = [action(resource="/networks/N1", operation="destroy")]
        with self.assertRaises(HardBlocked):
            tool.batch_stage(bad)
        self.assertEqual(calls, [])  # no HTTP call at all

    def test_action_missing_a_resource_is_rejected(self):
        tool, _ = self._tool([ok([{"id": "111"}]), ok([])])
        with self.assertRaises(MerakiError):
            tool.batch_stage([{"operation": "update", "body": {}}])

    def test_unrecognized_operation_does_not_silently_become_put(self):
        # The exact loophole from finding 1: "delete" is a plausible slip for
        # Meraki's actual "destroy" enum value. Before the fix this fell
        # through the {"create": ..., "update": ..., "destroy": ...}.get(op,
        # "PUT") default, became PUT, matched no HARD_BLOCKS entry (all keyed
        # on DELETE/POST/*), and would have been staged against the live API.
        tool, calls = self._tool([ok([{"id": "111"}]), ok([])])
        bad = [{"resource": "/networks/N1", "operation": "delete",
                "body": {}}]
        with self.assertRaises(MerakiError) as ctx:
            tool.batch_stage(bad)
        # HardBlocked is a MerakiError subclass, so assert on message content
        # to prove this was rejected by the operation check, not the hard
        # block (which never got the chance to run).
        self.assertNotIsInstance(ctx.exception, HardBlocked)
        self.assertIn("delete", str(ctx.exception))
        self.assertIn("/networks/N1", str(ctx.exception))
        self.assertEqual(calls, [])  # no HTTP call at all

    def test_absent_operation_is_rejected(self):
        tool, calls = self._tool([ok([{"id": "111"}]), ok([])])
        bad = [{"resource": "/networks/N1/appliance/vlans/10", "body": {}}]
        with self.assertRaises(MerakiError) as ctx:
            tool.batch_stage(bad)
        self.assertNotIsInstance(ctx.exception, HardBlocked)
        self.assertEqual(calls, [])  # no HTTP call at all

    def test_valid_operations_still_stage_successfully(self):
        for operation in ("create", "update", "destroy", "DESTROY"):
            with self.subTest(operation=operation):
                tool, calls = self._tool([
                    ok([{"id": "111"}]),
                    ok([]),
                    ok({"id": "B1", "status": {"completed": False,
                                               "failed": False}}),
                ])
                tool.batch_stage([action(operation=operation)])
                method, url, _ = calls[-1]
                self.assertEqual(method, "POST")
                self.assertIn("/organizations/111/actionBatches", url)

    def test_valid_destroy_operation_on_a_network_is_still_hard_blocked(self):
        # A *valid* operation ("destroy") that maps to a *correctly blocked*
        # method (DELETE) must still be refused. This guards against a
        # regression where fixing finding 1 (rejecting unrecognized
        # operations) accidentally routed valid operations around
        # check_hard_block instead of through it.
        tool, calls = self._tool([ok([{"id": "111"}]), ok([])])
        bad = [action(resource="/networks/N1", operation="destroy")]
        with self.assertRaises(HardBlocked):
            tool.batch_stage(bad)
        self.assertEqual(calls, [])  # no HTTP call at all


class TestBatchCommit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _tool(self, responses):
        http, calls = http_with(responses)
        return ConfigTool(http, snapshot_dir=self.tmp, now=lambda: "t"), calls

    def test_confirms_then_polls_to_completion(self):
        tool, calls = self._tool([
            ok([{"id": "111"}]),
            ok({"id": "B1", "status": {"completed": False, "failed": False}}),
            ok({"id": "B1", "status": {"completed": False, "failed": False}}),
            ok({"id": "B1", "status": {"completed": True, "failed": False,
                                       "errors": []}}),
        ])

        result = tool.batch_commit("B1", poll_interval=0, timeout=30)

        self.assertTrue(result["status"]["completed"])
        self.assertEqual(calls[1][0], "PUT")
        self.assertIs(json.loads(calls[1][2].decode())["confirmed"], True)

    def test_failed_batch_raises_with_the_server_errors(self):
        tool, _ = self._tool([
            ok([{"id": "111"}]),
            ok({"id": "B1", "status": {"completed": False, "failed": False}}),
            ok({"id": "B1", "status": {"completed": False, "failed": True,
                                       "errors": ["vlan 10 not found"]}}),
        ])
        with self.assertRaises(MerakiError) as ctx:
            tool.batch_commit("B1", poll_interval=0, timeout=30)
        self.assertIn("vlan 10 not found", str(ctx.exception))

    def test_timeout_raises_and_names_the_batch_id(self):
        stuck = [ok({"id": "B1", "status": {"completed": False,
                                            "failed": False}})] * 40
        tool, _ = self._tool([ok([{"id": "111"}])] + stuck)
        with self.assertRaises(MerakiError) as ctx:
            tool.batch_commit("B1", poll_interval=0, timeout=0)
        self.assertIn("B1", str(ctx.exception))


class TestBatchOutputRedaction(unittest.TestCase):
    # Meraki's action-batch API echoes submitted actions -- including each
    # action's body -- back in the batch object and in its error list. main()
    # prints batch-stage/batch-commit output through redact_secrets() (same
    # as apply/rollback) so a VPN PSK or RADIUS secret in an action body
    # never reaches stdout in the clear.
    #
    # Driving main() end-to-end here would require faking MerakiHTTP's
    # network layer at the module-construction boundary inside main() itself
    # (it builds its own MerakiHTTP(), unlike the tests above which inject
    # one directly into ConfigTool). That's more scaffolding than this
    # property needs, so this asserts redact_secrets() directly against a
    # batch-shaped payload representative of what Meraki echoes back --
    # the same function main() calls before printing.
    def test_secret_in_echoed_action_body_is_redacted(self):
        batch = {
            "id": "B1",
            "status": {"completed": True, "failed": False, "errors": []},
            "actions": [
                {"resource": "/networks/N1/appliance/vpn/site-to-site",
                 "operation": "update",
                 "body": {"subnets": [], "psk": "s3cr3t-vpn-key"}},
            ],
        }

        redacted = redact_secrets(batch)

        rendered = json.dumps(redacted)
        self.assertNotIn("s3cr3t-vpn-key", rendered)
        self.assertEqual(
            redacted["actions"][0]["body"]["psk"], "***REDACTED***")


if __name__ == "__main__":
    unittest.main()
