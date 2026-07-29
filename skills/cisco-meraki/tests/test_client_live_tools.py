import shutil
import tempfile
import unittest

import context  # noqa: F401

from helpers import http_with, ok
from meraki_http import MerakiError
from meraki_client import LIVE_TOOLS, MerakiClient, check_tool_supported


class TestToolSupport(unittest.TestCase):
    def test_cable_test_is_switch_only(self):
        check_tool_supported("cableTest", "MS225-48LP")  # must not raise
        with self.assertRaises(MerakiError) as ctx:
            check_tool_supported("cableTest", "MX67")
        self.assertIn("MX67", str(ctx.exception))

    def test_cable_test_allows_catalyst(self):
        check_tool_supported("cableTest", "C9300-24P")

    def test_throughput_test_rejects_switches(self):
        with self.assertRaises(MerakiError):
            check_tool_supported("throughputTest", "MS120-8")

    def test_ping_is_supported_everywhere_in_scope(self):
        for model in ("MX67", "MS225-48LP", "MR46"):
            check_tool_supported("ping", model)

    def test_unknown_tool_raises(self):
        with self.assertRaises(MerakiError):
            check_tool_supported("teleport", "MX67")

    def test_registry_has_no_out_of_scope_platforms(self):
        for prefixes in LIVE_TOOLS.values():
            for prefix in prefixes:
                self.assertNotIn(prefix, ("MV", "MT"))


class TestRunLiveTool(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.slept = []

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _client(self, extra, timeout=60.0):
        bootstrap = [
            ok([{"id": "111"}]),
            ok([{"serial": "Q2XX-1111-1111", "model": "MS225-48LP",
                 "name": "sw1"}]),
        ]
        http, calls = http_with(bootstrap + extra)
        client = MerakiClient(http, cache_dir=self.tmp)
        return client, calls

    def test_polls_until_complete(self):
        client, calls = self._client([
            ok({"cableTestId": "job-1", "status": "new"}),
            ok({"cableTestId": "job-1", "status": "running"}),
            ok({"cableTestId": "job-1", "status": "complete",
                "results": [{"port": "1", "status": "ok"}]}),
        ])
        result = client.run_live_tool(
            "cableTest", "Q2XX-1111-1111", {"ports": ["1"]},
            poll_interval=0, timeout=30,
        )
        self.assertEqual(result["status"], "complete")
        self.assertEqual(calls[2][0], "POST")
        self.assertEqual(calls[3][0], "GET")
        self.assertEqual(len(calls), 5)

    def test_failed_status_is_returned_not_raised(self):
        client, _ = self._client([
            ok({"cableTestId": "job-1", "status": "new"}),
            ok({"cableTestId": "job-1", "status": "failed",
                "error": "port down"}),
        ])
        result = client.run_live_tool("cableTest", "Q2XX-1111-1111",
                                      {"ports": ["1"]}, poll_interval=0)
        self.assertEqual(result["status"], "failed")

    def test_unsupported_model_refuses_before_any_call(self):
        bootstrap = [
            ok([{"id": "111"}]),
            ok([{"serial": "Q2XX-2222-2222", "model": "MS120-8", "name": "sw2"}]),
        ]
        http, calls = http_with(bootstrap)
        client = MerakiClient(http, cache_dir=self.tmp)
        with self.assertRaises(MerakiError):
            client.run_live_tool("throughputTest", "Q2XX-2222-2222")
        self.assertEqual(len(calls), 2)  # bootstrap only

    def test_unknown_serial_raises(self):
        client, _ = self._client([])
        with self.assertRaises(MerakiError):
            client.run_live_tool("ping", "Q2XX-9999-9999")

    def test_timeout_raises_rather_than_hanging(self):
        never_done = [ok({"cableTestId": "job-1", "status": "running"})] * 40
        client, _ = self._client(
            [ok({"cableTestId": "job-1", "status": "new"})] + never_done
        )
        with self.assertRaises(MerakiError) as ctx:
            client.run_live_tool("cableTest", "Q2XX-1111-1111", {"ports": ["1"]},
                                 poll_interval=0, timeout=0)
        self.assertIn("timed out", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
