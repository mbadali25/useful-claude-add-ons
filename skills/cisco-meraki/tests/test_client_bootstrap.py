import os
import shutil
import tempfile
import unittest

import context  # noqa: F401

from helpers import TEST_API_KEY, http_with, ok
from meraki_http import MerakiError
from meraki_client import (
    MerakiClient,
    max_timespan_for,
    parse_link_next,
    validate_timespan,
)


class TestParseLinkNext(unittest.TestCase):
    def test_extracts_next_url(self):
        header = ('<https://api.meraki.com/api/v1/x?startingAfter=1>; rel=first, '
                  '<https://api.meraki.com/api/v1/x?startingAfter=9>; rel=next')
        self.assertEqual(parse_link_next(header),
                         "https://api.meraki.com/api/v1/x?startingAfter=9")

    def test_returns_none_when_no_next(self):
        header = '<https://api.meraki.com/api/v1/x>; rel=first'
        self.assertIsNone(parse_link_next(header))

    def test_returns_none_for_missing_header(self):
        self.assertIsNone(parse_link_next(None))


class TestTimespanValidation(unittest.TestCase):
    def test_config_change_log_allows_365_days(self):
        path = "/organizations/O1/configurationChanges"
        self.assertEqual(max_timespan_for(path), 31536000)
        validate_timespan(path, 31536000)  # must not raise

    def test_default_endpoint_caps_at_31_days(self):
        self.assertEqual(max_timespan_for("/networks/N1/events"), 2678400)

    def test_over_limit_names_the_actual_limit(self):
        with self.assertRaises(MerakiError) as ctx:
            validate_timespan("/networks/N1/events", 9999999)
        self.assertIn("2678400", str(ctx.exception))


class TestOrgResolution(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_single_org_resolves(self):
        http, _ = http_with([ok([{"id": "111", "name": "Acme"}])])
        client = MerakiClient(http, cache_dir=self.tmp)
        self.assertEqual(client.resolve_org(), "111")

    def test_multiple_orgs_is_a_hard_stop_listing_them(self):
        http, _ = http_with([ok([{"id": "111", "name": "Acme"},
                                 {"id": "222", "name": "Beta"}])])
        client = MerakiClient(http, cache_dir=self.tmp)
        with self.assertRaises(MerakiError) as ctx:
            client.resolve_org()
        message = str(ctx.exception)
        self.assertIn("111", message)
        self.assertIn("222", message)

    def test_zero_orgs_is_an_error(self):
        http, _ = http_with([ok([])])
        client = MerakiClient(http, cache_dir=self.tmp)
        with self.assertRaises(MerakiError):
            client.resolve_org()

    def test_org_is_cached_after_first_call(self):
        http, calls = http_with([ok([{"id": "111", "name": "Acme"}])])
        client = MerakiClient(http, cache_dir=self.tmp)
        client.resolve_org()
        client.resolve_org()
        self.assertEqual(len(calls), 1)

    def test_cache_file_never_contains_the_api_key(self):
        http, _ = http_with([ok([{"id": "111", "name": "Acme"}])])
        client = MerakiClient(http, cache_dir=self.tmp)
        client.resolve_org()

        written = os.listdir(self.tmp)
        self.assertTrue(written, "expected a cache file to be written")
        blob = ""
        for name in written:
            with open(os.path.join(self.tmp, name), encoding="utf-8") as fh:
                blob += fh.read()

        self.assertIn("111", blob)              # the cache really has content
        self.assertNotIn(TEST_API_KEY, blob)    # but never the key


class TestNetworkLookup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_network_returns_cached_entry_with_product_types(self):
        http, _ = http_with([
            ok([{"id": "111"}]),
            ok([{"id": "N1", "name": "HQ",
                 "productTypes": ["appliance", "switch", "wireless"]}]),
        ])
        client = MerakiClient(http, cache_dir=self.tmp)
        net = client.network("N1")
        self.assertEqual(net["name"], "HQ")
        self.assertIn("switch", net["productTypes"])

    def test_unknown_network_raises(self):
        # Two networks calls: the initial fetch, then the one guaranteed
        # refetch-on-miss before the client concludes the network is
        # genuinely absent.
        http, _ = http_with([ok([{"id": "111"}]), ok([{"id": "N1"}]),
                             ok([{"id": "N1"}])])
        client = MerakiClient(http, cache_dir=self.tmp)
        with self.assertRaises(MerakiError):
            client.network("N-nope")

    def test_stale_cache_miss_refetches_and_succeeds(self):
        # Seed the on-disk cache so it only knows about N1, then look up N2,
        # which the (simulated) live API now returns. The lookup must not
        # raise a false "not in this org" from stale local state -- it should
        # refetch once and find it.
        http, calls = http_with([
            ok([{"id": "111"}]),
            ok([{"id": "N2", "name": "Branch"}]),
        ])
        client = MerakiClient(http, cache_dir=self.tmp)
        client.resolve_org()
        client._save_cache("111", {"networks": [{"id": "N1", "name": "HQ"}]})
        client._networks = None

        net = client.network("N2")

        self.assertEqual(net["name"], "Branch")
        networks_calls = [c for c in calls if c[1].endswith("/networks")]
        self.assertEqual(len(networks_calls), 1)

    def test_genuinely_absent_network_raises_and_refetches_exactly_once(self):
        http, calls = http_with([
            ok([{"id": "111"}]),
            ok([{"id": "N1"}]),
            ok([{"id": "N1"}]),
        ])
        client = MerakiClient(http, cache_dir=self.tmp)
        with self.assertRaises(MerakiError):
            client.network("N-nope")

        networks_calls = [c for c in calls if c[1].endswith("/networks")]
        self.assertEqual(len(networks_calls), 2)

    def test_force_bypasses_populated_cache(self):
        http, calls = http_with([
            ok([{"id": "111"}]),
            ok([{"id": "N1"}]),
            ok([{"id": "N1"}]),
        ])
        client = MerakiClient(http, cache_dir=self.tmp)
        client.networks()
        client.networks(force=True)

        networks_calls = [c for c in calls if c[1].endswith("/networks")]
        self.assertEqual(len(networks_calls), 2)


class TestPagination(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_get_all_follows_link_next_until_exhausted(self):
        page1 = ok([{"id": 1}], {"Link": '<https://api.meraki.com/api/v1/'
                                         'devices?startingAfter=1>; rel=next'})
        page2 = ok([{"id": 2}])
        http, calls = http_with([page1, page2])
        client = MerakiClient(http, cache_dir=self.tmp)

        items = client.get_all("/devices")

        self.assertEqual(items, [{"id": 1}, {"id": 2}])
        self.assertEqual(len(calls), 2)

    def test_get_all_does_not_inject_a_per_page_default(self):
        http, calls = http_with([ok([{"id": 1}])])
        client = MerakiClient(http, cache_dir=self.tmp)
        client.get_all("/devices")
        self.assertNotIn("perPage", calls[0][1])


if __name__ == "__main__":
    unittest.main()
