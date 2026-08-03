"""Read-only live smoke test. Skipped unless MERAKI_LIVE_TEST=1 and a key is set.

Never writes. Never asserts on tenant-specific values.
"""
import os
import unittest

import context  # noqa: F401  # pylint: disable=unused-import

from meraki_client import MerakiClient
from meraki_http import MerakiHTTP

ENABLED = os.environ.get("MERAKI_LIVE_TEST") == "1"
HAS_KEY = bool(os.environ.get("MERAKI_DASHBOARD_API_KEY"))


@unittest.skipUnless(ENABLED and HAS_KEY,
                     "set MERAKI_LIVE_TEST=1 and MERAKI_DASHBOARD_API_KEY")
class TestLiveSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = MerakiClient(MerakiHTTP())

    def test_bootstrap_resolves_one_org(self):
        self.assertTrue(self.client.resolve_org())

    def test_networks_are_listable(self):
        self.assertIsInstance(self.client.networks(), list)

    def test_device_statuses_are_listable(self):
        self.assertIsInstance(self.client.device_statuses(), list)

    def test_one_event_page_is_readable(self):
        nets = self.client.networks()
        if not nets:
            self.skipTest("org has no networks")
        for net in nets:
            usable = [p for p in (net.get("productTypes") or [])
                      if p in ("appliance", "switch", "wireless")]
            if usable:
                result = self.client.events(net["id"], product_type=usable[0],
                                            timespan=3600, per_page=3)
                self.assertIn("events", result)
                return
        self.skipTest("no in-scope network found")


if __name__ == "__main__":
    unittest.main()
