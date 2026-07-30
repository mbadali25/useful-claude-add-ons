import os
import unittest
import unittest.mock
import urllib.request

import context  # noqa: F401  -- puts scripts/ on sys.path

from helpers import TEST_API_KEY
from meraki_http import (
    DEFAULT_BASE_URL,
    MerakiError,
    MerakiHTTP,
    RateLimitError,
    _MethodPreservingRedirectHandler,
    redact,
)


class FakeSend:
    """Scripted stand-in for MerakiHTTP._send_urllib."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers, body))
        return self.responses.pop(0)


class RecordingSleep:
    def __init__(self):
        self.slept = []

    def __call__(self, seconds):
        self.slept.append(seconds)


class TestRedirectHandler(unittest.TestCase):
    def test_preserves_method_and_authorization_across_host(self):
        handler = _MethodPreservingRedirectHandler()
        req = urllib.request.Request(
            "https://api.meraki.com/api/v1/organizations/1/actionBatches",
            data=b'{"confirmed": false}',
            headers={"Authorization": f"Bearer {TEST_API_KEY}"},
            method="POST",
        )

        new = handler.redirect_request(
            req, None, 308, "Permanent Redirect", {},
            "https://n123.meraki.com/api/v1/organizations/1/actionBatches",
        )

        self.assertEqual(new.get_method(), "POST")
        self.assertEqual(new.data, b'{"confirmed": false}')
        self.assertEqual(new.get_header("Authorization"),
                         f"Bearer {TEST_API_KEY}")
        self.assertEqual(new.host, "n123.meraki.com")


class TestRequest(unittest.TestCase):
    def test_sends_bearer_header_and_parses_json(self):
        send = FakeSend([(200, {}, b'[{"id": "42"}]')])
        http = MerakiHTTP(api_key=TEST_API_KEY, _send=send)

        data, headers = http.request("GET", "/organizations")

        self.assertEqual(data, [{"id": "42"}])
        method, url, sent_headers, body = send.calls[0]
        self.assertEqual(method, "GET")
        self.assertEqual(url, DEFAULT_BASE_URL + "/organizations")
        self.assertEqual(sent_headers["Authorization"],
                         f"Bearer {TEST_API_KEY}")
        self.assertIsNone(body)

    def test_encodes_query_params(self):
        send = FakeSend([(200, {}, b"[]")])
        http = MerakiHTTP(api_key=TEST_API_KEY, _send=send)

        http.request("GET", "/networks/N1/events", params={"perPage": 5,
                                                           "productType": "switch"})

        _, url, _, _ = send.calls[0]
        self.assertIn("perPage=5", url)
        self.assertIn("productType=switch", url)

    def test_retries_on_429_honoring_retry_after(self):
        send = FakeSend([
            (429, {"Retry-After": "2"}, b'{"errors": ["rate limit"]}'),
            (200, {}, b'{"ok": true}'),
        ])
        sleep = RecordingSleep()
        http = MerakiHTTP(api_key=TEST_API_KEY, sleep=sleep, _send=send)

        data, _ = http.request("GET", "/organizations")

        self.assertEqual(data, {"ok": True})
        self.assertEqual(len(send.calls), 2)
        self.assertGreaterEqual(sleep.slept[0], 2)

    def test_raises_rate_limit_error_after_max_retries(self):
        send = FakeSend([(429, {"Retry-After": "1"}, b'{"errors": ["slow down"]}')
                        ] * 4)
        http = MerakiHTTP(api_key=TEST_API_KEY, sleep=RecordingSleep(),
                          max_retries=3, _send=send)

        with self.assertRaises(RateLimitError):
            http.request("GET", "/organizations")

    def test_maps_error_body_and_surfaces_request_id(self):
        send = FakeSend([
            (404, {"X-Request-Id": "abc-123"},
             b'{"errors": ["Network not found"]}'),
        ])
        http = MerakiHTTP(api_key=TEST_API_KEY, _send=send)

        with self.assertRaises(MerakiError) as ctx:
            http.request("GET", "/networks/nope/events")

        self.assertEqual(ctx.exception.status, 404)
        self.assertEqual(ctx.exception.messages, ["Network not found"])
        self.assertEqual(ctx.exception.request_id, "abc-123")
        self.assertIn("abc-123", str(ctx.exception))

    def test_missing_api_key_is_actionable(self):
        with unittest.mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(MerakiError) as ctx:
                MerakiHTTP(api_key=None, _send=FakeSend([]))
        self.assertIn("MERAKI_DASHBOARD_API_KEY", str(ctx.exception))


class TestRedact(unittest.TestCase):
    def test_replaces_api_key_occurrences(self):
        out = redact("failed with Bearer supersecret token", "supersecret")
        self.assertNotIn("supersecret", out)
        self.assertIn("***REDACTED***", out)

    def test_no_key_is_a_noop(self):
        self.assertEqual(redact("plain text", None), "plain text")


if __name__ == "__main__":
    unittest.main()
