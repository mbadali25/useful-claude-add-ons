import shutil
import tempfile
import unittest

import context  # noqa: F401

from helpers import http_with, ok
from meraki_http import MerakiError
from meraki_client import MerakiClient, product_type_for


class TestProductTypeFor(unittest.TestCase):
    def test_single_product_type_is_inferred(self):
        net = {"id": "N1", "productTypes": ["wireless"]}
        self.assertEqual(product_type_for(net), "wireless")

    def test_combined_network_without_choice_raises_listing_options(self):
        net = {"id": "N1", "productTypes": ["appliance", "switch", "wireless"]}
        with self.assertRaises(MerakiError) as ctx:
            product_type_for(net)
        message = str(ctx.exception)
        self.assertIn("appliance", message)
        self.assertIn("switch", message)
        self.assertIn("wireless", message)

    def test_explicit_choice_is_honored(self):
        net = {"id": "N1", "productTypes": ["appliance", "switch"]}
        self.assertEqual(product_type_for(net, "switch"), "switch")

    def test_explicit_choice_not_on_network_raises(self):
        net = {"id": "N1", "productTypes": ["appliance"]}
        with self.assertRaises(MerakiError):
            product_type_for(net, "wireless")

    def test_out_of_scope_product_type_is_rejected(self):
        net = {"id": "N1", "productTypes": ["camera"]}
        with self.assertRaises(MerakiError) as ctx:
            product_type_for(net, "camera")
        self.assertIn("scope", str(ctx.exception).lower())

    def test_network_with_only_out_of_scope_types_cannot_infer(self):
        net = {"id": "N1", "productTypes": ["camera", "sensor"]}
        with self.assertRaises(MerakiError) as ctx:
            product_type_for(net)
        self.assertIn("in-scope", str(ctx.exception).lower())


class TestEvents(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _client(self, extra):
        http, calls = http_with([
            ok([{"id": "111"}]),
            ok([{"id": "N1", "productTypes": ["appliance", "switch"]}]),
        ] + extra)
        return MerakiClient(http, cache_dir=self.tmp), calls

    def test_injects_product_type_for_combined_network(self):
        client, calls = self._client([ok({"events": []})])
        client.events("N1", product_type="switch")
        self.assertIn("productType=switch", calls[-1][1])

    def test_combined_network_without_product_type_fails_before_calling(self):
        client, calls = self._client([])
        with self.assertRaises(MerakiError):
            client.events("N1")
        self.assertEqual(len(calls), 2)  # bootstrap only, no events call

    def test_timespan_over_limit_is_rejected_before_calling(self):
        client, calls = self._client([])
        with self.assertRaises(MerakiError):
            client.events("N1", product_type="switch", timespan=9999999)
        self.assertEqual(len(calls), 2)


class TestOtherLogSurfaces(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_config_changes_targets_org_scope(self):
        http, calls = http_with([ok([{"id": "111"}]), ok([{"ts": "x"}])])
        client = MerakiClient(http, cache_dir=self.tmp)
        client.config_changes(timespan=86400)
        self.assertIn("/organizations/111/configurationChanges", calls[-1][1])

    def test_config_changes_accepts_a_full_year(self):
        http, calls = http_with([ok([{"id": "111"}]), ok([])])
        client = MerakiClient(http, cache_dir=self.tmp)

        result = client.config_changes(timespan=31536000)

        self.assertEqual(result, [])
        self.assertEqual(len(calls), 2)   # bootstrap + the changes call itself
        self.assertIn("timespan=31536000", calls[-1][1])

    def test_security_events_defaults_to_org_wide(self):
        http, calls = http_with([ok([{"id": "111"}]), ok([])])
        client = MerakiClient(http, cache_dir=self.tmp)
        client.security_events()
        self.assertIn("/organizations/111/appliance/security/events", calls[-1][1])

    def test_security_events_scoped_to_network_when_given(self):
        http, calls = http_with([ok([{"id": "111"}]),
                                 ok([{"id": "N1", "productTypes": ["appliance"]}]),
                                 ok([])])
        client = MerakiClient(http, cache_dir=self.tmp)
        client.security_events(network_id="N1")
        self.assertIn("/networks/N1/appliance/security/events", calls[-1][1])

    def test_air_marshal_requires_a_wireless_network(self):
        http, _ = http_with([ok([{"id": "111"}]),
                             ok([{"id": "N1", "productTypes": ["appliance"]}])])
        client = MerakiClient(http, cache_dir=self.tmp)
        with self.assertRaises(MerakiError) as ctx:
            client.air_marshal("N1")
        self.assertIn("wireless", str(ctx.exception).lower())

    def test_air_marshal_calls_wireless_endpoint(self):
        http, calls = http_with([ok([{"id": "111"}]),
                                 ok([{"id": "N1", "productTypes": ["wireless"]}]),
                                 ok([])])
        client = MerakiClient(http, cache_dir=self.tmp)
        client.air_marshal("N1", timespan=3600)
        self.assertIn("/networks/N1/wireless/airMarshal", calls[-1][1])


if __name__ == "__main__":
    unittest.main()
