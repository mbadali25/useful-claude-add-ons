import json
import shutil
import tempfile
import unittest

import context  # noqa: F401

from helpers import http_with, ok
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
        tool, calls = self._tool([ok([{"id": "111"}]), ok([])])
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


if __name__ == "__main__":
    unittest.main()
