import shutil
import tempfile
import unittest

import context  # noqa: F401  # pylint: disable=unused-import

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
        # A genuinely absent serial now costs one extra
        # /organizations/{id}/devices call: device() misses on the cached
        # list and refetches once (force=True) before concluding the serial
        # really isn't in this org. That refetch consumes one more queued
        # device-list response than before the refetch-once fix landed.
        client, _ = self._client([
            ok([{"serial": "Q2XX-1111-1111", "model": "MS225-48LP",
                 "name": "sw1"}]),
        ])
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

    def test_unlisted_job_id_key_still_polls(self):
        # "somethingElseId" is not in _JOB_ID_KEYS at all. The *Id-scanning
        # fallback must still find it and poll to completion.
        client, calls = self._client([
            ok({"somethingElseId": "job-9", "status": "new"}),
            ok({"somethingElseId": "job-9", "status": "complete",
                "results": []}),
        ])
        result = client.run_live_tool(
            "ping", "Q2XX-1111-1111", poll_interval=0, timeout=30,
        )
        self.assertEqual(result["status"], "complete")
        self.assertEqual(calls[2][0], "POST")
        self.assertEqual(calls[3][0], "GET")
        self.assertEqual(len(calls), 4)

    def test_no_usable_job_id_raises(self):
        # No key at all is *Id-shaped (or truthy). Old behavior returned this
        # payload unpolled, as if "status": "new" were a finished result.
        client, _ = self._client([
            ok({"status": "new"}),
        ])
        with self.assertRaises(MerakiError) as ctx:
            client.run_live_tool("ping", "Q2XX-1111-1111",
                                 poll_interval=0, timeout=30)
        self.assertIn("ping", str(ctx.exception))

    def test_ping_device_extracts_ping_device_id(self):
        client, _ = self._client([
            ok({"pingDeviceId": "job-42", "status": "new"}),
            ok({"pingDeviceId": "job-42", "status": "complete",
                "results": {"latencies": []}}),
        ])
        result = client.run_live_tool(
            "pingDevice", "Q2XX-1111-1111", poll_interval=0, timeout=30,
        )
        self.assertEqual(result["status"], "complete")

    def test_stale_device_cache_refetches_and_succeeds(self):
        # First device list is missing the target serial; the second
        # (post-refetch) list has it. device() must refetch once and find it.
        first_devices = ok([{"serial": "Q2XX-1111-1111",
                             "model": "MS225-48LP", "name": "sw1"}])
        second_devices = ok([
            {"serial": "Q2XX-1111-1111", "model": "MS225-48LP", "name": "sw1"},
            {"serial": "Q2XX-2222-2222", "model": "MS225-48LP", "name": "sw2"},
        ])
        http, calls = http_with([
            ok([{"id": "111"}]),
            first_devices,
            second_devices,
            ok({"cableTestId": "job-1", "status": "new"}),
            ok({"cableTestId": "job-1", "status": "complete", "results": []}),
        ])
        client = MerakiClient(http, cache_dir=self.tmp)
        result = client.run_live_tool(
            "cableTest", "Q2XX-2222-2222", {"ports": ["1"]},
            poll_interval=0, timeout=30,
        )
        self.assertEqual(result["status"], "complete")
        device_calls = [c for c in calls if c[1].endswith("/devices")]
        self.assertEqual(len(device_calls), 2)

    def test_absent_serial_raises_and_refetches_exactly_once(self):
        # A serial that is truly not in this org: device() misses on the
        # cached list, refetches once (force=True), misses again, and raises
        # -- proving there is no unbounded refetch loop.
        client, calls = self._client([
            ok([{"serial": "Q2XX-1111-1111", "model": "MS225-48LP",
                 "name": "sw1"}]),
        ])
        with self.assertRaises(MerakiError):
            client.run_live_tool("ping", "Q2XX-9999-9999")
        device_calls = [c for c in calls if c[1].endswith("/devices")]
        self.assertEqual(len(device_calls), 2)

    def test_convention_key_wins_over_ambiguous_response(self):
        # The tool-name convention (toolId) should be found and used even if
        # other *Id keys are present in the response. The response carries
        # both the convention key and an unrelated id, but only the
        # convention matches.
        client, calls = self._client([
            ok({"cableTestId": "job-convention", "networkId": "N1",
                "status": "new"}),
            ok({"cableTestId": "job-convention", "status": "complete",
                "results": []}),
        ])
        result = client.run_live_tool(
            "cableTest", "Q2XX-1111-1111", {"ports": ["1"]},
            poll_interval=0, timeout=30,
        )
        self.assertEqual(result["status"], "complete")
        # Verify that the correct job id was polled: check the GET URL
        poll_call = calls[3]
        self.assertEqual(poll_call[0], "GET")
        self.assertIn("job-convention", poll_call[1])

    def test_stray_resource_id_not_mistaken_for_job_id(self):
        # When the response carries only a resource id like networkId and no
        # job-id-shaped keys, the fallback must not mistake networkId for a
        # job id. It should raise an error about no recognizable job id.
        client, _ = self._client([
            ok({"networkId": "N1", "status": "new"}),
        ])
        with self.assertRaises(MerakiError) as ctx:
            client.run_live_tool("ping", "Q2XX-1111-1111",
                                 poll_interval=0, timeout=30)
        self.assertIn("no recognizable job id", str(ctx.exception))

    def test_ambiguous_id_candidates_raise_not_guess(self):
        # When the fallback scan finds multiple unrecognized *Id keys and
        # cannot determine which is the job id, it must raise an error
        # naming the ambiguous candidates rather than guessing.
        client, _ = self._client([
            ok({"fooId": "a", "barId": "b", "status": "new"}),
        ])
        with self.assertRaises(MerakiError) as ctx:
            client.run_live_tool("ping", "Q2XX-1111-1111",
                                 poll_interval=0, timeout=30)
        exc_str = str(ctx.exception)
        self.assertIn("multiple candidate", exc_str)
        self.assertIn("fooId", exc_str)
        self.assertIn("barId", exc_str)


if __name__ == "__main__":
    unittest.main()
