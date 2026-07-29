# Cisco Meraki Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `skills/cisco-meraki/` — a Claude Code skill that reads, diagnoses, and safely changes configuration on a single-organization Cisco Meraki estate (MX/MS/MR) through Dashboard API v1.

**Architecture:** Four stdlib-only Python modules. `meraki_http.py` owns transport (auth, method-preserving redirects, 429 backoff, error mapping). `meraki_client.py` is the read CLI plus live-tool jobs. `meraki_diff.py` owns semantic diffing, Meraki's implicit-default-rule quirk, and secret redaction. `meraki_config.py` is the *only* module that writes persistent config, and its `apply` control flow cannot reach a PUT without first snapshotting and rendering a diff.

**Tech Stack:** Python 3.9+ stdlib only (`urllib`, `json`, `argparse`, `unittest`). No pip installs, no third-party packages, no official Meraki SDK.

## Deviation from the spec (deliberate)

The spec's section 3 listed two scripts. This plan ships four. The spec's architectural commitment — read path separate from write path, write gate enforced by control flow — is preserved exactly. The extra split pulls shared transport out of both CLIs (otherwise duplicated) and isolates the diff engine, which carries the heaviest test load and the trickiest logic. `meraki_config.py` remains the sole module containing config-write calls, so the structural guarantee is unchanged.

## Global Constraints

- Base URL: `https://api.meraki.com/api/v1`
- Auth: `Authorization: Bearer <key>`, key read **only** from env `MERAKI_DASHBOARD_API_KEY`. Never echoed, never accepted from chat, never written to any file.
- Python: stdlib only. No `requests`, no `meraki` SDK, no pip install step.
- Tests: stdlib `unittest`. No pytest. This repo currently has zero test infrastructure; this plan creates it.
- Test command (from repo root): `python -m unittest discover -s skills/cisco-meraki/tests -p "test_*.py" -v`
- Rate limit: 10 req/sec per org. On `429`, honor `Retry-After` then exponential backoff with jitter.
- Snapshot/cache directory: `.meraki-snapshots/` — gitignored.
- Action batch caps enforced client-side: 100 actions per batch, 5 pending batches per org.
- Product scope: MX, MS/Catalyst, MR only. No MV, MT, or SM endpoints anywhere.
- Every mutating operation snapshots first, renders a diff, and requires confirmation. No exceptions.
- Hard-blocked outright: delete network, delete org, remove/unclaim device, revoke admin, rotate/delete API key.

## File Structure

| File | Responsibility |
|---|---|
| `skills/cisco-meraki/SKILL.md` | Frontmatter + skimmable body: bootstrap, script usage, reference map, safety rails |
| `skills/cisco-meraki/scripts/meraki_http.py` | Transport only: auth header, method-preserving redirects, 429 backoff, error mapping, `X-Request-Id` surfacing |
| `skills/cisco-meraki/scripts/meraki_client.py` | Read CLI: bootstrap cache, pagination, logs, live-tool jobs |
| `skills/cisco-meraki/scripts/meraki_diff.py` | Semantic diff, implicit-default-rule strip/re-derive, secret redaction |
| `skills/cisco-meraki/scripts/meraki_config.py` | Write CLI: snapshot, apply, rollback, action batches, hard-block enforcement |
| `skills/cisco-meraki/tests/context.py` | Puts `scripts/` on `sys.path` for tests |
| `skills/cisco-meraki/tests/helpers.py` | Shared test fixtures: `ok()`, `http_with()`, `rule()`, `DEFAULT_RULE` |
| `skills/cisco-meraki/tests/test_*.py` | One test module per script module |
| `skills/cisco-meraki/references/*.md` | 8 deep-dive docs, read on demand |

---

### Task 1: Transport core

**Files:**
- Create: `skills/cisco-meraki/scripts/meraki_http.py`
- Create: `skills/cisco-meraki/tests/context.py`
- Create: `skills/cisco-meraki/tests/helpers.py`
- Test: `skills/cisco-meraki/tests/test_http.py`

**Interfaces:**
- Consumes: nothing (first task)
- Produces (from `tests/helpers.py`, used by every later test module — do not
  redefine these per module):
  - `TEST_API_KEY = "test-key-abc123def456"` — multi-character on purpose, so
    leak assertions can search for it without false positives
  - `ok(payload, headers=None) -> tuple[int, dict, bytes]`
  - `http_with(responses) -> tuple[MerakiHTTP, list[tuple[str, str, bytes | None]]]`
    — `calls` always records `(method, url, body)`
  - `rule(policy, dest, comment="r") -> dict`
  - `DEFAULT_RULE: dict` — Meraki's implicit trailing allow-any rule
- Produces (from `scripts/meraki_http.py`):
  - `MerakiError(Exception)` with attributes `status: int`, `messages: list[str]`, `request_id: str | None`
  - `RateLimitError(MerakiError)`
  - `redact(text: str, api_key: str | None) -> str`
  - `MerakiHTTP(api_key: str | None = None, base_url: str = DEFAULT_BASE_URL, sleep=time.sleep, max_retries: int = 5, _send=None)`
  - `MerakiHTTP.request(method: str, path: str, params: dict | None = None, body: object | None = None) -> tuple[object, dict]` returning `(parsed_json, response_headers)`
  - `_MethodPreservingRedirectHandler` (used by Task 1 only, tested directly)
  - `DEFAULT_BASE_URL: str`
  - The injectable `_send(method, url, headers, body_bytes) -> tuple[int, dict, bytes]` seam that all later tests fake

- [ ] **Step 1: Create the test path helper**

Create `skills/cisco-meraki/tests/context.py`:

```python
"""Puts the skill's scripts/ directory on sys.path so tests can import it."""
import os
import sys

SCRIPTS = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, "scripts")
)
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)
```

- [ ] **Step 1b: Create the shared test helpers**

Every later test module imports these. Do not redefine them per module.

Create `skills/cisco-meraki/tests/helpers.py`:

```python
"""Shared fixtures for the Meraki skill's tests.

http_with() fakes the injectable _send seam on MerakiHTTP, so no test ever
opens a socket. `calls` always records (method, url, body) -- tests that don't
care about the body simply ignore the third element.
"""
import json

import context  # noqa: F401  -- puts scripts/ on sys.path

from meraki_http import MerakiHTTP

# Multi-character on purpose: a single-letter key makes "did this leak?"
# assertions produce false positives against ordinary JSON.
TEST_API_KEY = "test-key-abc123def456"


def ok(payload, headers=None):
    """A 200 response carrying JSON."""
    return (200, headers or {}, json.dumps(payload).encode())


def http_with(responses):
    """MerakiHTTP wired to a scripted response queue.

    Returns (http, calls) where calls accumulates (method, url, body).
    """
    queue = list(responses)
    calls = []

    def send(method, url, headers, body):
        calls.append((method, url, body))
        return queue.pop(0)

    return MerakiHTTP(api_key=TEST_API_KEY, _send=send), calls


def rule(policy, dest, comment="r"):
    """An MX L3 firewall rule."""
    return {
        "comment": comment,
        "policy": policy,
        "protocol": "any",
        "srcCidr": "Any",
        "srcPort": "Any",
        "destCidr": dest,
        "destPort": "Any",
        "syslogEnabled": False,
    }


# Meraki's implicit trailing rule: GET returns it, PUT rejects it.
DEFAULT_RULE = {
    "comment": "Default rule",
    "policy": "allow",
    "protocol": "Any",
    "srcCidr": "Any",
    "srcPort": "Any",
    "destCidr": "Any",
    "destPort": "Any",
}
```

- [ ] **Step 2: Write the failing tests**

Create `skills/cisco-meraki/tests/test_http.py`:

```python
import unittest
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
        send = FakeSend([(429, {"Retry-After": "1"}, b'{"errors": ["slow down"]}')] * 4)
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m unittest discover -s skills/cisco-meraki/tests -p "test_http.py" -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'meraki_http'`

- [ ] **Step 4: Implement the transport**

Create `skills/cisco-meraki/scripts/meraki_http.py`:

```python
#!/usr/bin/env python3
"""
meraki_http.py -- transport layer for the Cisco Meraki Dashboard API v1.

Stdlib only. Owns exactly four concerns and nothing else:

  * Bearer auth from MERAKI_DASHBOARD_API_KEY (never from an argument in chat)
  * Redirects that preserve HTTP method AND the Authorization header. urllib's
    default handler downgrades POST->GET on 301/302 and can drop Authorization
    on a cross-host redirect; Meraki may 308 to a shard host, so both matter.
  * 429 handling: honor Retry-After, then exponential backoff with jitter.
  * Error mapping: Meraki returns {"errors": [...]}; surface X-Request-Id
    because Meraki support asks for it.

This module never writes configuration. See meraki_config.py for that.
"""

import json
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE_URL = "https://api.meraki.com/api/v1"
API_KEY_ENV = "MERAKI_DASHBOARD_API_KEY"
REDACTION = "***REDACTED***"


def redact(text, api_key):
    """Remove the API key from any string bound for output."""
    if not api_key or not text:
        return text
    return text.replace(api_key, REDACTION)


class MerakiError(Exception):
    def __init__(self, status, messages, request_id=None):
        self.status = status
        self.messages = list(messages) if messages else []
        self.request_id = request_id
        detail = "; ".join(self.messages) or "(no message)"
        suffix = f" [X-Request-Id: {request_id}]" if request_id else ""
        super().__init__(f"HTTP {status}: {detail}{suffix}")


class RateLimitError(MerakiError):
    pass


class _MethodPreservingRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follow redirects without changing the method or losing auth headers."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return urllib.request.Request(
            newurl,
            data=req.data,
            headers=dict(req.header_items()),
            origin_req_host=req.origin_req_host,
            unverifiable=True,
            method=req.get_method(),
        )


class MerakiHTTP:
    def __init__(self, api_key=None, base_url=DEFAULT_BASE_URL,
                 sleep=time.sleep, max_retries=5, _send=None):
        self.api_key = api_key if api_key is not None else os.environ.get(API_KEY_ENV)
        if not self.api_key:
            raise MerakiError(
                0,
                [f"No API key. Export {API_KEY_ENV} in your shell; "
                 f"do not paste the key into chat."],
            )
        self.base_url = base_url.rstrip("/")
        self.sleep = sleep
        self.max_retries = max_retries
        self._send = _send or self._send_urllib
        self._opener = urllib.request.build_opener(_MethodPreservingRedirectHandler())

    def _send_urllib(self, method, url, headers, body):
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with self._opener.open(req, timeout=60) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers or {}), exc.read()

    def request(self, method, path, params=None, body=None):
        url = self.base_url + path
        if params:
            clean = {k: v for k, v in params.items() if v is not None}
            if clean:
                url += "?" + urllib.parse.urlencode(clean, doseq=True)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "User-Agent": "claude-code-meraki-skill/1.0",
        }
        payload = None
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        for attempt in range(self.max_retries):
            status, resp_headers, raw = self._send(method, url, headers, payload)
            request_id = resp_headers.get("X-Request-Id")

            if status == 429:
                if attempt == self.max_retries - 1:
                    break
                self.sleep(self._backoff(resp_headers, attempt))
                continue

            if status >= 400:
                raise MerakiError(status, self._messages(raw), request_id)

            if not raw:
                return None, resp_headers
            return json.loads(raw.decode("utf-8")), resp_headers

        raise RateLimitError(429, [f"Rate limited after {self.max_retries} attempts"],
                             request_id)

    def _backoff(self, resp_headers, attempt):
        try:
            base = float(resp_headers.get("Retry-After", 1))
        except (TypeError, ValueError):
            base = 1.0
        return base + (2 ** attempt) * 0.1 + random.uniform(0, 0.25)

    def _messages(self, raw):
        if not raw:
            return []
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return [redact(raw.decode("utf-8", "replace")[:400], self.api_key)]
        if isinstance(parsed, dict) and "errors" in parsed:
            return [redact(str(m), self.api_key) for m in parsed["errors"]]
        return [redact(json.dumps(parsed)[:400], self.api_key)]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m unittest discover -s skills/cisco-meraki/tests -p "test_http.py" -v`

Expected: PASS — 9 tests

- [ ] **Step 6: Commit**

```bash
git add skills/cisco-meraki/scripts/meraki_http.py skills/cisco-meraki/tests/context.py skills/cisco-meraki/tests/helpers.py skills/cisco-meraki/tests/test_http.py
git commit -m "feat(meraki): transport layer with method-preserving redirects and 429 backoff"
```

Note: `test_http.py` keeps its own `FakeSend` class rather than using
`helpers.http_with`. That is deliberate, not duplication — `http_with`
*constructs* a `MerakiHTTP`, which is the object under test here, and these
tests need to inspect the request **headers** that `http_with` discards.

---

### Task 2: Bootstrap, cache, and pagination

**Files:**
- Create: `skills/cisco-meraki/scripts/meraki_client.py`
- Test: `skills/cisco-meraki/tests/test_client_bootstrap.py`
- Modify: `.gitignore` (append `.meraki-snapshots/`)

**Interfaces:**
- Consumes: `MerakiHTTP`, `MerakiError` from `meraki_http`
- Produces:
  - `CACHE_DIR = ".meraki-snapshots"`
  - `parse_link_next(link_header: str | None) -> str | None`
  - `max_timespan_for(path: str) -> int`
  - `validate_timespan(path: str, timespan: int | None) -> None` — raises `MerakiError`
  - `MerakiClient(http: MerakiHTTP, cache_dir: str = CACHE_DIR)`
  - `MerakiClient.resolve_org() -> str` — hard-stops on multiple orgs
  - `MerakiClient.networks() -> list[dict]`
  - `MerakiClient.network(network_id: str) -> dict`
  - `MerakiClient.device_statuses() -> list[dict]`
  - `MerakiClient.inventory() -> list[dict]`
  - `MerakiClient.get(path: str, params: dict | None = None) -> object`
  - `MerakiClient.get_all(path: str, params: dict | None = None) -> list`

- [ ] **Step 1: Write the failing tests**

Create `skills/cisco-meraki/tests/test_client_bootstrap.py`:

```python
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
        http, _ = http_with([ok([{"id": "111"}]), ok([{"id": "N1"}])])
        client = MerakiClient(http, cache_dir=self.tmp)
        with self.assertRaises(MerakiError):
            client.network("N-nope")


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest discover -s skills/cisco-meraki/tests -p "test_client_bootstrap.py" -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'meraki_client'`

- [ ] **Step 3: Implement bootstrap, cache, and pagination**

Create `skills/cisco-meraki/scripts/meraki_client.py`:

```python
#!/usr/bin/env python3
"""
meraki_client.py -- read-only client for the Cisco Meraki Dashboard API v1.

Handles every GET, plus live-tool jobs (which POST but create only ephemeral
diagnostics and mutate no stored configuration). This module contains no
persistent-config write path at all -- that lives in meraki_config.py, and
keeping the two apart is what makes the snapshot/diff gate structural rather
than a rule someone has to remember.

Env:
    MERAKI_DASHBOARD_API_KEY   required

CLI examples:
    python meraki_client.py orgs
    python meraki_client.py networks
    python meraki_client.py status
    python meraki_client.py inventory
    python meraki_client.py get /networks/N1/appliance/vlans
    python meraki_client.py get-all /organizations/O1/devices
"""

import argparse
import json
import os
import sys
import urllib.parse

from meraki_http import MerakiError, MerakiHTTP

CACHE_DIR = ".meraki-snapshots"

# Per-endpoint timespan ceilings, in seconds. Meraki rejects anything larger
# with an opaque 400, so validate client-side and quote the real limit.
_TIMESPAN_365_DAYS = 31536000
_TIMESPAN_31_DAYS = 2678400


def max_timespan_for(path):
    if "/configurationChanges" in path:
        return _TIMESPAN_365_DAYS
    return _TIMESPAN_31_DAYS


def validate_timespan(path, timespan):
    if timespan is None:
        return
    limit = max_timespan_for(path)
    if int(timespan) > limit:
        raise MerakiError(
            0,
            [f"timespan {timespan}s exceeds the {limit}s maximum for {path}. "
             f"Use t0/t1 to window a longer period, or lower --timespan."],
        )


def parse_link_next(link_header):
    """Pull the rel=next URL out of an RFC 5988 Link header."""
    if not link_header:
        return None
    for part in link_header.split(","):
        segments = part.split(";")
        if len(segments) < 2:
            continue
        url = segments[0].strip()
        if not (url.startswith("<") and url.endswith(">")):
            continue
        for attr in segments[1:]:
            key, _, value = attr.strip().partition("=")
            if key.strip() == "rel" and value.strip().strip('"') == "next":
                return url[1:-1]
    return None


class MerakiClient:
    def __init__(self, http, cache_dir=CACHE_DIR):
        self.http = http
        self.cache_dir = cache_dir
        self._org_id = None
        self._networks = None

    # ---- cache -----------------------------------------------------------

    def _cache_path(self, org_id):
        return os.path.join(self.cache_dir, f".cache-{org_id}.json")

    def _load_cache(self, org_id):
        path = self._cache_path(org_id)
        if not os.path.exists(path):
            return {}
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return {}

    def _save_cache(self, org_id, data):
        os.makedirs(self.cache_dir, exist_ok=True)
        with open(self._cache_path(org_id), "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)

    # ---- bootstrap -------------------------------------------------------

    def resolve_org(self):
        if self._org_id:
            return self._org_id
        orgs, _ = self.http.request("GET", "/organizations")
        if not orgs:
            raise MerakiError(
                0, ["This API key can see no organizations. Confirm the key is "
                    "valid and that Organization > Settings > Dashboard API "
                    "access is enabled."])
        if len(orgs) > 1:
            listed = ", ".join(f"{o.get('name')} ({o.get('id')})" for o in orgs)
            raise MerakiError(
                0, [f"This skill is scoped to a single organization but the key "
                    f"sees {len(orgs)}: {listed}. Re-run with the intended org "
                    f"confirmed by the user."])
        self._org_id = str(orgs[0]["id"])
        cache = self._load_cache(self._org_id)
        cache["org"] = {"id": self._org_id, "name": orgs[0].get("name")}
        self._save_cache(self._org_id, cache)
        return self._org_id

    def networks(self):
        if self._networks is not None:
            return self._networks
        org_id = self.resolve_org()
        cache = self._load_cache(org_id)
        if cache.get("networks"):
            self._networks = cache["networks"]
            return self._networks
        nets, _ = self.http.request("GET", f"/organizations/{org_id}/networks")
        self._networks = nets or []
        cache["networks"] = self._networks
        self._save_cache(org_id, cache)
        return self._networks

    def network(self, network_id):
        for net in self.networks():
            if str(net.get("id")) == str(network_id):
                return net
        known = ", ".join(str(n.get("id")) for n in self.networks()) or "(none)"
        raise MerakiError(0, [f"Network {network_id} is not in this org. "
                              f"Known network IDs: {known}"])

    def device_statuses(self):
        org_id = self.resolve_org()
        return self.get_all(f"/organizations/{org_id}/devices/statuses")

    def inventory(self):
        org_id = self.resolve_org()
        return self.get_all(f"/organizations/{org_id}/inventory/devices")

    # ---- generic reads ---------------------------------------------------

    def get(self, path, params=None):
        if params:
            validate_timespan(path, params.get("timespan"))
        data, _ = self.http.request("GET", path, params=params)
        return data

    def get_all(self, path, params=None):
        """Follow Link: rel=next. Never injects a perPage default -- the caps
        differ per endpoint (1000 on some, 50 or 5 on others), so the server's
        own default and Link header are treated as authoritative."""
        if params:
            validate_timespan(path, params.get("timespan"))
        items = []
        next_path = path
        next_params = params
        while next_path:
            data, headers = self.http.request("GET", next_path, params=next_params)
            if isinstance(data, list):
                items.extend(data)
            elif data is not None:
                items.append(data)
            next_url = parse_link_next(headers.get("Link"))
            if not next_url:
                break
            parsed = urllib.parse.urlsplit(next_url)
            next_path = parsed.path
            if next_path.startswith("/api/v1"):
                next_path = next_path[len("/api/v1"):]
            next_params = dict(urllib.parse.parse_qsl(parsed.query)) or None
        return items


def _emit(data):
    json.dump(data, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


def build_parser():
    parser = argparse.ArgumentParser(description="Meraki Dashboard API read client")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("orgs")
    sub.add_parser("networks")
    sub.add_parser("status")
    sub.add_parser("inventory")
    for name in ("get", "get-all"):
        p = sub.add_parser(name)
        p.add_argument("path")
        p.add_argument("--params", default=None,
                       help="URL-encoded query string, e.g. 'timespan=3600'")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    client = MerakiClient(MerakiHTTP())
    try:
        if args.command == "orgs":
            _emit(client.get("/organizations"))
        elif args.command == "networks":
            _emit(client.networks())
        elif args.command == "status":
            _emit(client.device_statuses())
        elif args.command == "inventory":
            _emit(client.inventory())
        else:
            params = dict(urllib.parse.parse_qsl(args.params)) if args.params else None
            fn = client.get if args.command == "get" else client.get_all
            _emit(fn(args.path, params))
    except MerakiError as exc:
        sys.exit(str(exc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest discover -s skills/cisco-meraki/tests -p "test_client_bootstrap.py" -v`

Expected: PASS — 15 tests

- [ ] **Step 5: Gitignore the snapshot and cache directory**

Append to `.gitignore`:

```gitignore

# Cisco Meraki skill — config snapshots and bootstrap cache (may contain
# network config and shared secrets; never commit)
.meraki-snapshots/
```

- [ ] **Step 6: Commit**

```bash
git add skills/cisco-meraki/scripts/meraki_client.py skills/cisco-meraki/tests/test_client_bootstrap.py .gitignore
git commit -m "feat(meraki): bootstrap, org/network cache, and Link-header pagination"
```

---

### Task 3: Log surfaces

**Files:**
- Modify: `skills/cisco-meraki/scripts/meraki_client.py` (add methods + subcommands)
- Test: `skills/cisco-meraki/tests/test_client_logs.py`

**Interfaces:**
- Consumes: `MerakiClient`, `validate_timespan`, `MerakiError`
- Produces:
  - `product_type_for(network: dict, requested: str | None = None) -> str`
  - `MerakiClient.events(network_id: str, product_type: str | None = None, timespan: int | None = None, per_page: int | None = None) -> dict`
  - `MerakiClient.config_changes(timespan: int | None = None) -> list`
  - `MerakiClient.security_events(network_id: str | None = None, timespan: int | None = None) -> list`
  - `MerakiClient.air_marshal(network_id: str, timespan: int | None = None) -> list`

- [ ] **Step 1: Write the failing tests**

Create `skills/cisco-meraki/tests/test_client_logs.py`:

```python
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
        http, _ = http_with([ok([{"id": "111"}]), ok([])])
        client = MerakiClient(http, cache_dir=self.tmp)
        client.config_changes(timespan=31536000)  # must not raise

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest discover -s skills/cisco-meraki/tests -p "test_client_logs.py" -v`

Expected: FAIL — `ImportError: cannot import name 'product_type_for'`

- [ ] **Step 3: Add the log surfaces**

In `skills/cisco-meraki/scripts/meraki_client.py`, add after `parse_link_next`:

```python
# MX/MS/MR only. MV cameras, MT sensors, and SM are out of this skill's scope.
IN_SCOPE_PRODUCT_TYPES = ("appliance", "switch", "wireless")


def product_type_for(network, requested=None):
    """Resolve the productType the event-log endpoint requires.

    Combined networks need it explicitly; omitting it returns a 404 that reads
    like the network does not exist, which is the single most confusing error
    in this API.
    """
    available = list(network.get("productTypes") or [])
    if requested:
        if requested not in available:
            raise MerakiError(
                0, [f"Network {network.get('id')} has no '{requested}' product "
                    f"type. Available: {', '.join(available) or '(none)'}"])
        if requested not in IN_SCOPE_PRODUCT_TYPES:
            raise MerakiError(
                0, [f"Product type '{requested}' is outside this skill's scope "
                    f"(MX/MS/MR only)."])
        return requested

    usable = [p for p in available if p in IN_SCOPE_PRODUCT_TYPES]
    if not usable:
        raise MerakiError(
            0, [f"Network {network.get('id')} has no in-scope product types. "
                f"Found: {', '.join(available) or '(none)'}"])
    if len(usable) > 1:
        raise MerakiError(
            0, [f"Network {network.get('id')} is a combined network "
                f"({', '.join(usable)}). The event log requires one "
                f"productType -- pass --product-type with one of these."])
    return usable[0]
```

Then add these methods to `MerakiClient`, after `inventory`:

```python
    # ---- log surfaces ----------------------------------------------------

    def events(self, network_id, product_type=None, timespan=None, per_page=None):
        net = self.network(network_id)
        resolved = product_type_for(net, product_type)
        path = f"/networks/{network_id}/events"
        validate_timespan(path, timespan)
        params = {"productType": resolved, "timespan": timespan,
                  "perPage": per_page}
        return self.get(path, params)

    def config_changes(self, timespan=None):
        org_id = self.resolve_org()
        path = f"/organizations/{org_id}/configurationChanges"
        validate_timespan(path, timespan)
        return self.get_all(path, {"timespan": timespan})

    def security_events(self, network_id=None, timespan=None):
        if network_id:
            net = self.network(network_id)
            if "appliance" not in (net.get("productTypes") or []):
                raise MerakiError(
                    0, [f"Network {network_id} has no MX appliance, so it has no "
                        f"security events."])
            path = f"/networks/{network_id}/appliance/security/events"
        else:
            org_id = self.resolve_org()
            path = f"/organizations/{org_id}/appliance/security/events"
        validate_timespan(path, timespan)
        return self.get_all(path, {"timespan": timespan})

    def air_marshal(self, network_id, timespan=None):
        net = self.network(network_id)
        if "wireless" not in (net.get("productTypes") or []):
            raise MerakiError(
                0, [f"Network {network_id} has no wireless product type, so "
                    f"Air Marshal is unavailable."])
        path = f"/networks/{network_id}/wireless/airMarshal"
        validate_timespan(path, timespan)
        return self.get_all(path, {"timespan": timespan})
```

Then in `build_parser`, before the `return parser` line:

```python
    events = sub.add_parser("events")
    events.add_argument("--network", required=True)
    events.add_argument("--product-type", default=None,
                        choices=list(IN_SCOPE_PRODUCT_TYPES))
    events.add_argument("--timespan", type=int, default=None)
    events.add_argument("--per-page", type=int, default=None)

    changes = sub.add_parser("changes")
    changes.add_argument("--timespan", type=int, default=None)

    secev = sub.add_parser("security-events")
    secev.add_argument("--network", default=None)
    secev.add_argument("--timespan", type=int, default=None)

    marshal = sub.add_parser("air-marshal")
    marshal.add_argument("--network", required=True)
    marshal.add_argument("--timespan", type=int, default=None)
```

And in `main`, insert these branches before the final `else`:

```python
        elif args.command == "events":
            _emit(client.events(args.network, args.product_type,
                                args.timespan, args.per_page))
        elif args.command == "changes":
            _emit(client.config_changes(args.timespan))
        elif args.command == "security-events":
            _emit(client.security_events(args.network, args.timespan))
        elif args.command == "air-marshal":
            _emit(client.air_marshal(args.network, args.timespan))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest discover -s skills/cisco-meraki/tests -p "test_client_logs.py" -v`

Expected: PASS — 14 tests

- [ ] **Step 5: Run the whole suite for regressions**

Run: `python -m unittest discover -s skills/cisco-meraki/tests -p "test_*.py" -v`

Expected: PASS — 38 tests (9 http + 15 bootstrap + 14 logs)

- [ ] **Step 6: Commit**

```bash
git add skills/cisco-meraki/scripts/meraki_client.py skills/cisco-meraki/tests/test_client_logs.py
git commit -m "feat(meraki): event log, config change log, security events, Air Marshal"
```

---

### Task 4: Live diagnostic tools

**Files:**
- Modify: `skills/cisco-meraki/scripts/meraki_client.py`
- Test: `skills/cisco-meraki/tests/test_client_live_tools.py`

**Interfaces:**
- Consumes: `MerakiClient`, `MerakiError`
- Produces:
  - `LIVE_TOOLS: dict[str, tuple[str, ...]]` — tool name → supported model prefixes
  - `TERMINAL_STATUSES = ("complete", "failed")`
  - `check_tool_supported(tool: str, model: str) -> None` — raises `MerakiError`
  - `MerakiClient.device(serial: str) -> dict`
  - `MerakiClient.run_live_tool(tool: str, serial: str, body: dict | None = None, timeout: float = 60.0, poll_interval: float = 2.0) -> dict`

- [ ] **Step 1: Write the failing tests**

Create `skills/cisco-meraki/tests/test_client_live_tools.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest discover -s skills/cisco-meraki/tests -p "test_client_live_tools.py" -v`

Expected: FAIL — `ImportError: cannot import name 'LIVE_TOOLS'`

- [ ] **Step 3: Add live tools**

In `skills/cisco-meraki/scripts/meraki_client.py`, add `import time` to the imports, then add after `product_type_for`:

```python
# Live-tool availability is platform-bound. Checking the model up front turns a
# bare 400 into an actionable refusal. Verify this table against the live API
# during implementation -- Meraki adds tools over time.
LIVE_TOOLS = {
    "ping": ("MX", "MS", "MR", "MG", "Z", "C9"),
    "pingDevice": ("MX", "MS", "MR", "MG", "Z", "C9"),
    "cableTest": ("MS", "C9"),
    "throughputTest": ("MX", "MR", "Z"),
    "arpTable": ("MX", "MS", "C9"),
    "macTable": ("MS", "C9"),
    "wakeOnLan": ("MX", "MS", "C9"),
}

TERMINAL_STATUSES = ("complete", "failed")

# Response key holding the job id, per tool.
_JOB_ID_KEYS = ("pingId", "cableTestId", "throughputTestId", "arpTableId",
                "macTableId", "wakeOnLanId", "id")


def check_tool_supported(tool, model):
    if tool not in LIVE_TOOLS:
        raise MerakiError(
            0, [f"Unknown live tool '{tool}'. Available: "
                f"{', '.join(sorted(LIVE_TOOLS))}"])
    prefixes = LIVE_TOOLS[tool]
    upper = (model or "").upper()
    if not any(upper.startswith(p) for p in prefixes):
        raise MerakiError(
            0, [f"Live tool '{tool}' is not available on {model}. "
                f"Supported platforms: {', '.join(prefixes)}"])
```

Then add these methods to `MerakiClient`, after `air_marshal`:

```python
    # ---- live tools (ephemeral jobs; no persistent config change) --------

    def device(self, serial):
        org_id = self.resolve_org()
        cache = self._load_cache(org_id)
        devices = cache.get("devices")
        if not devices:
            devices = self.get_all(f"/organizations/{org_id}/devices")
            cache["devices"] = devices
            self._save_cache(org_id, cache)
        for dev in devices:
            if str(dev.get("serial")) == str(serial):
                return dev
        raise MerakiError(0, [f"Serial {serial} is not in this org's device list."])

    def run_live_tool(self, tool, serial, body=None, timeout=60.0,
                      poll_interval=2.0):
        dev = self.device(serial)
        check_tool_supported(tool, dev.get("model", ""))

        base = f"/devices/{serial}/liveTools/{tool}"
        created, _ = self.http.request("POST", base, body=body or {})
        job_id = None
        for key in _JOB_ID_KEYS:
            if isinstance(created, dict) and created.get(key):
                job_id = created[key]
                break
        if not job_id:
            return created

        deadline = time.monotonic() + float(timeout)
        latest = created
        while True:
            latest, _ = self.http.request("GET", f"{base}/{job_id}")
            status = (latest or {}).get("status")
            if status in TERMINAL_STATUSES:
                return latest
            if time.monotonic() >= deadline:
                raise MerakiError(
                    0, [f"Live tool '{tool}' on {serial} timed out after "
                        f"{timeout}s; last status was '{status}'. "
                        f"Job id {job_id} can still be polled manually."])
            if poll_interval:
                time.sleep(poll_interval)
```

Then in `build_parser`, before `return parser`:

```python
    live = sub.add_parser("live")
    live.add_argument("tool", choices=sorted(LIVE_TOOLS))
    live.add_argument("serial")
    live.add_argument("--json", dest="body", default=None,
                     help='Tool body, e.g. \'{"target": "8.8.8.8"}\'')
    live.add_argument("--timeout", type=float, default=60.0)
```

And in `main`, before the final `else`:

```python
        elif args.command == "live":
            body = json.loads(args.body) if args.body else None
            _emit(client.run_live_tool(args.tool, args.serial, body,
                                       timeout=args.timeout))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest discover -s skills/cisco-meraki/tests -p "test_client_live_tools.py" -v`

Expected: PASS — 11 tests

- [ ] **Step 5: Commit**

```bash
git add skills/cisco-meraki/scripts/meraki_client.py skills/cisco-meraki/tests/test_client_live_tools.py
git commit -m "feat(meraki): live diagnostic tools with model gating and poll timeout"
```

---

### Task 5: Semantic diff, default-rule handling, redaction

**Files:**
- Create: `skills/cisco-meraki/scripts/meraki_diff.py`
- Test: `skills/cisco-meraki/tests/test_diff.py`

**Interfaces:**
- Consumes: nothing (pure functions, no HTTP)
- Produces:
  - `SECRET_KEYS: frozenset[str]`
  - `is_default_l3_rule(rule: dict) -> bool`
  - `strip_default_rule(rules: list[dict]) -> list[dict]`
  - `redact_secrets(obj) -> object` — deep copy, secret values replaced
  - `rule_key(rule: dict) -> str`
  - `diff_rules(current: list[dict], proposed: list[dict]) -> list[tuple[str, int, dict]]` — ops are `"added"`, `"removed"`, `"moved"`, `"changed"`; position is 1-based
  - `render_diff(lines: list[tuple[str, int, dict]]) -> str`

- [ ] **Step 1: Write the failing tests**

Create `skills/cisco-meraki/tests/test_diff.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest discover -s skills/cisco-meraki/tests -p "test_diff.py" -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'meraki_diff'`

- [ ] **Step 3: Implement the diff engine**

Create `skills/cisco-meraki/scripts/meraki_diff.py`:

```python
#!/usr/bin/env python3
"""
meraki_diff.py -- semantic diffing for Meraki config, plus secret redaction.

Two Meraki-specific behaviors live here because getting either wrong corrupts
production config:

1. Ordered rule sets. Meraki firewall and ACL rules are evaluated in order, so
   position IS semantics. Moving a deny above a permit changes behavior while
   set membership stays identical -- a set-based diff would report "no change"
   on a reorder that breaks the network. diff_rules() is therefore positional.

2. The implicit default rule. GET on L3 firewall rules returns Meraki's
   trailing "Default rule" allow-any entry, but PUT REJECTS it in the payload.
   Unhandled, a snapshot->PUT round trip fails outright and every diff shows a
   phantom removal. strip_default_rule() removes it on read; the caller
   re-derives it implicitly by simply not sending it. Do not "fix" this by
   passing the default rule through -- the API will reject the write.
"""

import copy
import json

SECRET_KEYS = frozenset({
    "psk", "secret", "sharedsecret", "passphrase", "password",
    "privatekey", "authkey", "presharedkey", "radiussecret",
})

REDACTION = "***REDACTED***"

_DEFAULT_RULE_COMMENTS = {"default rule"}


def is_default_l3_rule(rule):
    """True for Meraki's implicit trailing allow-any default rule."""
    if not isinstance(rule, dict):
        return False
    if (rule.get("comment") or "").strip().lower() not in _DEFAULT_RULE_COMMENTS:
        return False
    if (rule.get("policy") or "").lower() != "allow":
        return False
    wildcards = ("srcCidr", "destCidr", "srcPort", "destPort", "protocol")
    return all((rule.get(k) or "").lower() == "any" for k in wildcards)


def strip_default_rule(rules):
    """Drop a trailing implicit default rule. Never mutates the input."""
    out = list(rules or [])
    if out and is_default_l3_rule(out[-1]):
        return out[:-1]
    return out


def redact_secrets(obj):
    """Deep copy with any secret-bearing value replaced."""
    if isinstance(obj, dict):
        return {
            k: (REDACTION if k.lower() in SECRET_KEYS else redact_secrets(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [redact_secrets(v) for v in obj]
    return copy.copy(obj)


def rule_key(rule):
    """Stable, hashable identity for a rule, independent of dict key order."""
    return json.dumps(rule, sort_keys=True, default=str)


def diff_rules(current, proposed):
    """Positional diff over two ordered rule lists.

    Returns a list of (op, position, rule) where op is one of
    "added" / "removed" / "moved" / "changed" and position is 1-based.
    Empty list means genuinely no change.
    """
    cur = list(current or [])
    prop = list(proposed or [])
    cur_keys = [rule_key(r) for r in cur]
    prop_keys = [rule_key(r) for r in prop]

    if cur_keys == prop_keys:
        return []

    cur_set = set(cur_keys)
    prop_set = set(prop_keys)

    # Same membership, different order: a pure reorder. Report every position
    # that shifted -- this is the case a set-based diff would silently miss.
    if cur_set == prop_set and len(cur_keys) == len(prop_keys):
        return [
            ("moved", i + 1, prop[i])
            for i, (c, p) in enumerate(zip(cur_keys, prop_keys))
            if c != p
        ]

    lines = []
    # Positions present in both lists but holding different rules: an in-place
    # edit rather than an add plus a remove.
    for i in range(min(len(cur_keys), len(prop_keys))):
        if cur_keys[i] == prop_keys[i]:
            continue
        if prop_keys[i] not in cur_set and cur_keys[i] not in prop_set:
            lines.append(("changed", i + 1, prop[i]))

    changed_positions = {pos for _, pos, _ in lines}

    for i, key in enumerate(prop_keys):
        if key not in cur_set and (i + 1) not in changed_positions:
            lines.append(("added", i + 1, prop[i]))
    for i, key in enumerate(cur_keys):
        if key not in prop_set and (i + 1) not in changed_positions:
            lines.append(("removed", i + 1, cur[i]))

    lines.sort(key=lambda item: (item[1], item[0]))
    return lines


_PREFIX = {"added": "+", "removed": "-", "moved": "~", "changed": "~"}


def render_diff(lines):
    """Human-readable diff. Always redacts secrets -- a diff gets pasted into
    tickets, so a PSK must never appear here even though the snapshot keeps it.
    """
    if not lines:
        return "no change"
    out = []
    for op, position, rule in lines:
        safe = redact_secrets(rule)
        body = json.dumps(safe, sort_keys=True, default=str)
        note = " (moved)" if op == "moved" else ""
        out.append(f"{_PREFIX[op]} [{position}]{note} {body}")
    return "\n".join(out)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest discover -s skills/cisco-meraki/tests -p "test_diff.py" -v`

Expected: PASS — 21 tests

- [ ] **Step 5: Commit**

```bash
git add skills/cisco-meraki/scripts/meraki_diff.py skills/cisco-meraki/tests/test_diff.py
git commit -m "feat(meraki): positional semantic diff, default-rule handling, secret redaction"
```

---

### Task 6: Write CLI — snapshot, apply, rollback, hard blocks

**Files:**
- Create: `skills/cisco-meraki/scripts/meraki_config.py`
- Test: `skills/cisco-meraki/tests/test_config.py`

**Interfaces:**
- Consumes: `MerakiHTTP`, `MerakiError` from `meraki_http`; `diff_rules`, `render_diff`, `strip_default_rule`, `redact_secrets` from `meraki_diff`
- Produces:
  - `SNAPSHOT_DIR = ".meraki-snapshots"`
  - `HardBlocked(MerakiError)`
  - `HARD_BLOCKS: tuple[tuple[str, str, str], ...]` — (method, regex, reason)
  - `check_hard_block(method: str, path: str) -> None` — raises `HardBlocked`
  - `extract_rules(payload) -> list[dict]`
  - `ConfigTool(http: MerakiHTTP, snapshot_dir: str = SNAPSHOT_DIR, now=None)`
  - `ConfigTool.snapshot(path: str) -> str` — returns snapshot file path
  - `ConfigTool.diff(path: str, proposed: object) -> list`
  - `ConfigTool.apply(path: str, proposed: object, confirm) -> dict` — `confirm(diff_text) -> bool`
  - `ConfigTool.rollback(snapshot_path: str, confirm) -> dict`

- [ ] **Step 1: Write the failing tests**

Create `skills/cisco-meraki/tests/test_config.py`:

```python
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
            tool.apply("/networks/N1", {}, confirm=lambda text: True)
        self.assertEqual(calls, [])

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest discover -s skills/cisco-meraki/tests -p "test_config.py" -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'meraki_config'`

- [ ] **Step 3: Implement the write CLI**

Create `skills/cisco-meraki/scripts/meraki_config.py`:

```python
#!/usr/bin/env python3
"""
meraki_config.py -- the ONLY path that writes persistent Meraki configuration.

Meraki's collection endpoints are full-replacement PUTs: sending three firewall
rules does not add three rules, it deletes every rule absent from the payload.
So apply() is built so it CANNOT reach a PUT without first snapshotting current
state and rendering a diff for confirmation. That is control flow, not a rule
someone has to remember -- do not add a bare put() helper to this module.

Env:
    MERAKI_DASHBOARD_API_KEY   required

CLI examples:
    python meraki_config.py snapshot /networks/N1/appliance/firewall/l3FirewallRules
    python meraki_config.py diff /networks/N1/appliance/firewall/l3FirewallRules new.json
    python meraki_config.py apply /networks/N1/appliance/firewall/l3FirewallRules new.json
    python meraki_config.py rollback .meraki-snapshots/20260729-120000_....json
"""

import argparse
import datetime
import json
import os
import re
import sys

from meraki_diff import (
    diff_rules,
    redact_secrets,
    render_diff,
    strip_default_rule,
)
from meraki_http import MerakiError, MerakiHTTP

SNAPSHOT_DIR = ".meraki-snapshots"


class HardBlocked(MerakiError):
    pass


# Operations refused outright regardless of confirmation, because a snapshot
# cannot restore them. These require the Dashboard UI.
HARD_BLOCKS = (
    ("DELETE", r"^/networks/[^/]+/?$",
     "Deleting a network destroys all of its configuration and history."),
    ("DELETE", r"^/organizations/[^/]+/?$",
     "Deleting an organization is irreversible."),
    ("POST", r"^/networks/[^/]+/devices/remove",
     "Removing a device from a network loses its per-network configuration."),
    ("POST", r"^/organizations/[^/]+/inventory/release",
     "Releasing a device from inventory unclaims it from the organization."),
    ("DELETE", r"^/organizations/[^/]+/admins/",
     "Revoking admin access can lock out the operator running this skill."),
    ("*", r"/identities/me/api/keys",
     "API key rotation or revocation must be done by a human in Dashboard."),
)


def check_hard_block(method, path):
    for blocked_method, pattern, reason in HARD_BLOCKS:
        if blocked_method not in ("*", method.upper()):
            continue
        if re.search(pattern, path):
            raise HardBlocked(
                0,
                [f"Refusing {method} {path}. {reason} Do this in the Meraki "
                 f"Dashboard UI if it is genuinely intended."],
            )


def extract_rules(payload):
    """Normalize a config payload into an ordered list for diffing."""
    if isinstance(payload, dict) and isinstance(payload.get("rules"), list):
        return payload["rules"]
    if isinstance(payload, list):
        return payload
    if payload is None:
        return []
    return [payload]


def _repack(original, rules):
    """Put a diffed rule list back into the shape the endpoint expects."""
    if isinstance(original, dict) and isinstance(original.get("rules"), list):
        out = dict(original)
        out["rules"] = rules
        return out
    if isinstance(original, list):
        return rules
    return original


def _default_now():
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


class ConfigTool:
    def __init__(self, http, snapshot_dir=SNAPSHOT_DIR, now=None):
        self.http = http
        self.snapshot_dir = snapshot_dir
        self.now = now or _default_now

    # ---- snapshot --------------------------------------------------------

    def snapshot(self, path):
        """GET current state and write it verbatim (secrets included) to disk.

        Secrets are preserved here on purpose -- a rollback must be able to
        restore a working PSK. The directory is gitignored, and render_diff()
        redacts anything displayed.
        """
        check_hard_block("GET", path)
        payload, _ = self.http.request("GET", path)
        os.makedirs(self.snapshot_dir, exist_ok=True)
        slug = re.sub(r"[^A-Za-z0-9]+", "-", path).strip("-")[:90]
        filename = f"{self.now()}_{slug}.json"
        full = os.path.join(self.snapshot_dir, filename)
        with open(full, "w", encoding="utf-8") as fh:
            json.dump({"path": path, "captured": self.now(),
                       "payload": payload}, fh, indent=2, default=str)
        return full

    # ---- diff ------------------------------------------------------------

    def diff(self, path, proposed):
        current, _ = self.http.request("GET", path)
        return self._diff_payloads(current, proposed)

    def _diff_payloads(self, current, proposed):
        current_rules = strip_default_rule(extract_rules(current))
        proposed_rules = strip_default_rule(extract_rules(proposed))
        return diff_rules(current_rules, proposed_rules)

    # ---- apply -----------------------------------------------------------

    def apply(self, path, proposed, confirm):
        """Snapshot, diff, confirm, then PUT. There is no path to the PUT that
        skips the first three steps."""
        check_hard_block("PUT", path)

        snapshot_path = self.snapshot(path)
        with open(snapshot_path, encoding="utf-8") as fh:
            current = json.load(fh)["payload"]

        lines = self._diff_payloads(current, proposed)
        if not lines:
            raise MerakiError(
                0, [f"Proposed config for {path} is identical to live state "
                    f"(no change). Nothing written. "
                    f"Snapshot kept at {snapshot_path}"])

        rendered = render_diff(lines)
        if not confirm(rendered):
            raise MerakiError(
                0, [f"Change to {path} declined. Nothing written. "
                    f"Snapshot kept at {snapshot_path}"])

        body = _repack(proposed, strip_default_rule(extract_rules(proposed)))
        result, _ = self.http.request("PUT", path, body=body)
        return {"path": path, "snapshot": snapshot_path,
                "changes": len(lines), "result": result}

    # ---- rollback --------------------------------------------------------

    def rollback(self, snapshot_path, confirm):
        if not os.path.exists(snapshot_path):
            raise MerakiError(0, [f"No snapshot at {snapshot_path}"])
        with open(snapshot_path, encoding="utf-8") as fh:
            saved = json.load(fh)
        path = saved["path"]
        return self.apply(path, saved["payload"], confirm)


def _confirm_interactively(rendered):
    sys.stderr.write("\nProposed change:\n" + rendered + "\n\n")
    sys.stderr.write("Apply this change? [y/N] ")
    sys.stderr.flush()
    return sys.stdin.readline().strip().lower() in ("y", "yes")


def _load_json_file(filename):
    with open(filename, encoding="utf-8") as fh:
        return json.load(fh)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Meraki Dashboard API config write tool")
    sub = parser.add_subparsers(dest="command", required=True)

    snap = sub.add_parser("snapshot")
    snap.add_argument("path")

    diff_cmd = sub.add_parser("diff")
    diff_cmd.add_argument("path")
    diff_cmd.add_argument("proposed")

    apply_cmd = sub.add_parser("apply")
    apply_cmd.add_argument("path")
    apply_cmd.add_argument("proposed")
    apply_cmd.add_argument("--yes", action="store_true",
                           help="Skip the interactive prompt. The diff is "
                                "still rendered to stderr.")

    rb = sub.add_parser("rollback")
    rb.add_argument("snapshot")
    rb.add_argument("--yes", action="store_true")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    tool = ConfigTool(MerakiHTTP())
    try:
        if args.command == "snapshot":
            print(tool.snapshot(args.path))
        elif args.command == "diff":
            print(render_diff(tool.diff(args.path,
                                        _load_json_file(args.proposed))))
        elif args.command == "apply":
            confirm = _auto_confirm if args.yes else _confirm_interactively
            result = tool.apply(args.path, _load_json_file(args.proposed),
                                confirm)
            json.dump(redact_secrets(result), sys.stdout, indent=2, default=str)
            sys.stdout.write("\n")
        elif args.command == "rollback":
            confirm = _auto_confirm if args.yes else _confirm_interactively
            result = tool.rollback(args.snapshot, confirm)
            json.dump(redact_secrets(result), sys.stdout, indent=2, default=str)
            sys.stdout.write("\n")
    except MerakiError as exc:
        sys.exit(str(exc))
    return 0


def _auto_confirm(rendered):
    sys.stderr.write("\nApplying change:\n" + rendered + "\n")
    return True


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest discover -s skills/cisco-meraki/tests -p "test_config.py" -v`

Expected: PASS — 23 tests

- [ ] **Step 5: Commit**

```bash
git add skills/cisco-meraki/scripts/meraki_config.py skills/cisco-meraki/tests/test_config.py
git commit -m "feat(meraki): snapshot/diff/apply/rollback with hard-block enforcement"
```

---

### Task 7: Action batches

**Files:**
- Modify: `skills/cisco-meraki/scripts/meraki_config.py`
- Test: `skills/cisco-meraki/tests/test_config_batches.py`

**Interfaces:**
- Consumes: `ConfigTool`, `check_hard_block`, `MerakiError`
- Produces:
  - `MAX_BATCH_ACTIONS = 100`
  - `MAX_PENDING_BATCHES = 5`
  - `ConfigTool.batch_stage(actions: list[dict], org_id: str | None = None) -> dict`
  - `ConfigTool.batch_commit(batch_id: str, org_id: str | None = None, timeout: float = 120.0, poll_interval: float = 2.0) -> dict`
  - `ConfigTool.resolve_org() -> str`

- [ ] **Step 1: Write the failing tests**

Create `skills/cisco-meraki/tests/test_config_batches.py`:

```python
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
        self.assertEqual(len(calls), 2)  # no POST attempted

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest discover -s skills/cisco-meraki/tests -p "test_config_batches.py" -v`

Expected: FAIL — `ImportError: cannot import name 'MAX_BATCH_ACTIONS'`

- [ ] **Step 3: Add action batch support**

In `skills/cisco-meraki/scripts/meraki_config.py`, add `import time` to the imports, then add after the `SNAPSHOT_DIR` line:

```python
# Client-side caps so a too-large batch fails locally with a clear message
# rather than as an opaque server rejection. Verify against the live API.
MAX_BATCH_ACTIONS = 100
MAX_PENDING_BATCHES = 5
```

Then add these methods to `ConfigTool`, after `rollback`:

```python
    # ---- action batches --------------------------------------------------

    def resolve_org(self):
        if getattr(self, "_org_id", None):
            return self._org_id
        orgs, _ = self.http.request("GET", "/organizations")
        if not orgs:
            raise MerakiError(0, ["This API key can see no organizations."])
        if len(orgs) > 1:
            listed = ", ".join(f"{o.get('name')} ({o.get('id')})" for o in orgs)
            raise MerakiError(
                0, [f"This skill is scoped to a single organization but the key "
                    f"sees {len(orgs)}: {listed}."])
        self._org_id = str(orgs[0]["id"])
        return self._org_id

    def batch_stage(self, actions, org_id=None):
        """Stage a batch with confirmed:false so Meraki validates the whole
        payload server-side before anything commits. The returned batch's own
        error list is the dry-run result."""
        if not actions:
            raise MerakiError(0, ["No actions supplied; nothing to stage."])
        if len(actions) > MAX_BATCH_ACTIONS:
            raise MerakiError(
                0, [f"{len(actions)} actions exceeds the {MAX_BATCH_ACTIONS}-"
                    f"action limit per batch. Split into multiple batches."])

        for item in actions:
            resource = item.get("resource")
            if not resource:
                raise MerakiError(
                    0, [f"Action is missing 'resource': {item}"])
            operation = (item.get("operation") or "").lower()
            method = {"create": "POST", "update": "PUT",
                      "destroy": "DELETE"}.get(operation, "PUT")
            check_hard_block(method, resource)

        org = org_id or self.resolve_org()
        pending = self._pending_batches(org)
        if len(pending) >= MAX_PENDING_BATCHES:
            raise MerakiError(
                0, [f"{len(pending)} batches are already pending, at the "
                    f"{MAX_PENDING_BATCHES}-batch limit. Commit or delete one "
                    f"in Dashboard before staging another."])

        body = {"confirmed": False, "synchronous": False, "actions": actions}
        batch, _ = self.http.request(
            "POST", f"/organizations/{org}/actionBatches", body=body)
        return batch

    def _pending_batches(self, org_id):
        batches, _ = self.http.request(
            "GET", f"/organizations/{org_id}/actionBatches",
            params={"status": "pending"})
        return batches or []

    def batch_commit(self, batch_id, org_id=None, timeout=120.0,
                     poll_interval=2.0):
        org = org_id or self.resolve_org()
        path = f"/organizations/{org}/actionBatches/{batch_id}"
        self.http.request("PUT", path, body={"confirmed": True})

        deadline = time.monotonic() + float(timeout)
        while True:
            batch, _ = self.http.request("GET", path)
            status = (batch or {}).get("status") or {}
            if status.get("failed"):
                errors = status.get("errors") or ["(no detail returned)"]
                raise MerakiError(
                    0, [f"Action batch {batch_id} failed: "
                        f"{'; '.join(str(e) for e in errors)}"])
            if status.get("completed"):
                return batch
            if time.monotonic() >= deadline:
                raise MerakiError(
                    0, [f"Action batch {batch_id} did not complete within "
                        f"{timeout}s. It may still be running -- poll "
                        f"{path} to check."])
            if poll_interval:
                time.sleep(poll_interval)
```

Then in `build_parser`, before `return parser`:

```python
    stage = sub.add_parser("batch-stage")
    stage.add_argument("actions", help="JSON file holding a list of actions")

    commit = sub.add_parser("batch-commit")
    commit.add_argument("batch_id")
    commit.add_argument("--timeout", type=float, default=120.0)
```

And in `main`, before the `except` clause:

```python
        elif args.command == "batch-stage":
            batch = tool.batch_stage(_load_json_file(args.actions))
            json.dump(batch, sys.stdout, indent=2, default=str)
            sys.stdout.write("\n")
        elif args.command == "batch-commit":
            batch = tool.batch_commit(args.batch_id, timeout=args.timeout)
            json.dump(batch, sys.stdout, indent=2, default=str)
            sys.stdout.write("\n")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest discover -s skills/cisco-meraki/tests -p "test_config_batches.py" -v`

Expected: PASS — 9 tests

- [ ] **Step 5: Run the whole suite**

Run: `python -m unittest discover -s skills/cisco-meraki/tests -p "test_*.py" -v`

Expected: PASS — 102 tests (9 http + 15 bootstrap + 14 logs + 11 live tools + 21 diff + 23 config + 9 batches)

- [ ] **Step 6: Commit**

```bash
git add skills/cisco-meraki/scripts/meraki_config.py skills/cisco-meraki/tests/test_config_batches.py
git commit -m "feat(meraki): staged action batches with cap enforcement and commit polling"
```

---

### Task 8: SKILL.md and reference documents

**Files:**
- Create: `skills/cisco-meraki/SKILL.md`
- Create: `skills/cisco-meraki/references/auth-and-bootstrap.md`
- Create: `skills/cisco-meraki/references/inventory-and-status.md`
- Create: `skills/cisco-meraki/references/appliance-mx.md`
- Create: `skills/cisco-meraki/references/switch-ms.md`
- Create: `skills/cisco-meraki/references/wireless-mr.md`
- Create: `skills/cisco-meraki/references/logs-and-events.md`
- Create: `skills/cisco-meraki/references/live-tools.md`
- Create: `skills/cisco-meraki/references/change-safety.md`

**Interfaces:**
- Consumes: the CLI surface of `meraki_client.py` and `meraki_config.py` as built in Tasks 1–7. Every example command in the docs must match a real subcommand from those two `build_parser()` functions.
- Produces: no code. `SKILL.md` frontmatter `name: cisco-meraki`.

- [ ] **Step 1: Write SKILL.md**

Create `skills/cisco-meraki/SKILL.md`:

```markdown
---
name: cisco-meraki
description: >
  Work with a Cisco Meraki organization through the Dashboard API v1 — inventory
  and device status, network event log, org configuration change log, MX security
  and IDS events, Air Marshal rogue APs, live diagnostics (ping, cable test,
  throughput, ARP/MAC table, wake-on-LAN), and configuration changes to MX
  appliances, MS/Catalyst switches, and MR access points with snapshot/diff/
  confirm and rollback on every write. Use this skill whenever the user mentions
  Meraki, Cisco Meraki, the Meraki Dashboard, an MX/MS/MR device, a Meraki serial
  (Q2xx-xxxx-xxxx), or api.meraki.com — and also when they describe the work
  without naming the product: "which APs are offline", "who changed the firewall
  rules", "why is this switch port flapping", "cycle port 12", "what broke since
  Friday", "add a VLAN", "is that site's VPN up". Also use it when troubleshooting
  a 429 rate limit from api.meraki.com, or a 404 from the Meraki event log that is
  actually a missing productType on a combined network.
---

# Cisco Meraki Dashboard API

Read, diagnose, and safely change a single Meraki organization over Dashboard API
v1 at `https://api.meraki.com/api/v1`. Scope is MX, MS/Catalyst, and MR. Cameras
(MV), sensors (MT), and Systems Manager are out of scope — say so rather than
improvising against those endpoints.

## The one thing to internalize first

Meraki collection endpoints are **full-replacement PUTs**. `PUT` on
`/networks/{id}/appliance/firewall/l3FirewallRules` with three rules does not add
three rules — it deletes every rule not in the payload. Never hand-write a `PUT`.
Always go through `scripts/meraki_config.py`, which snapshots, diffs, and confirms
before it writes.

## Quick start

```bash
export MERAKI_DASHBOARD_API_KEY=...        # never paste the key into chat
python scripts/meraki_client.py orgs       # validates the key, resolves the org
python scripts/meraki_client.py networks   # network map, cached
python scripts/meraki_client.py status     # org-wide online/offline/alerting
```

Those three calls are the bootstrap. Results cache to `.meraki-snapshots/` so
routine work costs four calls total, not four per question.

If `orgs` returns more than one organization, stop and ask the user which one —
this skill is scoped to a single org and will refuse to guess.

## Reading

```bash
python scripts/meraki_client.py inventory
python scripts/meraki_client.py get /networks/N_1/appliance/vlans
python scripts/meraki_client.py get-all /organizations/O_1/devices
python scripts/meraki_client.py events --network N_1 --product-type switch --timespan 3600
python scripts/meraki_client.py changes --timespan 86400
python scripts/meraki_client.py security-events --timespan 86400
python scripts/meraki_client.py air-marshal --network N_1 --timespan 3600
python scripts/meraki_client.py live ping Q2XX-1111-1111 --json '{"target":"8.8.8.8"}'
python scripts/meraki_client.py live cableTest Q2XX-1111-1111 --json '{"ports":["12"]}'
```

`events` needs `--product-type` on a combined network. Omitting it returns a `404`
that reads like the network does not exist; the client catches this and tells you
which product types the network actually has.

## Changing configuration

```bash
python scripts/meraki_config.py snapshot /networks/N_1/appliance/firewall/l3FirewallRules
python scripts/meraki_config.py diff /networks/N_1/appliance/firewall/l3FirewallRules proposed.json
python scripts/meraki_config.py apply /networks/N_1/appliance/firewall/l3FirewallRules proposed.json
python scripts/meraki_config.py rollback .meraki-snapshots/20260729-120000_networks-N-1-....json
```

`apply` cannot write without first snapshotting and rendering a diff — that is its
control flow, not a rule you have to remember. Show the user the rendered diff and
get explicit agreement before confirming.

For anything touching multiple networks or devices, stage a batch so Meraki
validates the whole payload server-side first:

```bash
python scripts/meraki_config.py batch-stage actions.json   # confirmed:false
python scripts/meraki_config.py batch-commit B_1
```

Read the staged batch's error list back to the user as the dry-run result before
committing. Caps: 100 actions per batch, 5 pending batches per org.

## Reference map

| Task | Reference |
|---|---|
| API key setup, org API access, bootstrap, rate limits, redirects | `references/auth-and-bootstrap.md` |
| Inventory, device status, uplink health, licensing models | `references/inventory-and-status.md` |
| MX: VLANs, L3/L7 firewall, static routes, site-to-site VPN, content filtering, traffic shaping | `references/appliance-mx.md` |
| MS: port config/status, ACLs, STP, QoS, stacks, L3 interfaces, port cycling | `references/switch-ms.md` |
| MR: SSIDs, RF profiles, radio settings, client connectivity and latency | `references/wireless-mr.md` |
| Event log, config change log, security events, Air Marshal | `references/logs-and-events.md` |
| Ping, cable test, throughput, ARP/MAC table, wake-on-LAN | `references/live-tools.md` |
| Snapshot/diff/rollback, action batches, hard blocks, the default-rule trap | `references/change-safety.md` |

Read the relevant reference before writing calls — each carries exact paths,
payload shapes, and the per-endpoint quirks.

## Safety rails

- **Never hand-write a config `PUT`.** Use `meraki_config.py`.
- **Show the diff, not a count.** "3 rules will change" is not informed consent;
  the rendered diff is.
- **Refused outright**, regardless of confirmation, because no snapshot can undo
  them: delete network, delete organization, remove/unclaim a device, revoke admin
  access, rotate or delete an API key. These need the Dashboard UI.
- **Never echo the API key.** It comes from `MERAKI_DASHBOARD_API_KEY` only. If the
  user pastes a key into chat, tell them to rotate it.
- **Snapshots contain live secrets** (VPN PSKs, RADIUS secrets). They live in the
  gitignored `.meraki-snapshots/`. Displayed diffs redact secrets; snapshot files
  do not, because rollback needs them intact. Never paste a snapshot file into a
  ticket or commit one.
- **Rate limit is 10 req/sec per org.** The client backs off on `429`
  automatically; don't defeat it with parallel invocations.
```

- [ ] **Step 2: Verify every SKILL.md command against the real parsers**

Run:

```bash
python skills/cisco-meraki/scripts/meraki_client.py --help
python skills/cisco-meraki/scripts/meraki_config.py --help
```

Expected: both print usage listing exactly the subcommands used in `SKILL.md` —
client: `orgs, networks, status, inventory, get, get-all, events, changes,
security-events, air-marshal, live`; config: `snapshot, diff, apply, rollback,
batch-stage, batch-commit`. Fix any mismatch in `SKILL.md`, not in the parser.

- [ ] **Step 3: Write the eight reference documents**

Each reference is a focused deep-dive. Write them with real paths and payload
shapes — no placeholders. Required content per file:

`references/auth-and-bootstrap.md`
- Generating a key: Dashboard → My Profile → API access. The key inherits that
  user's Dashboard permissions; there is no separate API RBAC. Recommend a
  dedicated least-privilege service account.
- Enabling org access: Organization → Settings → Dashboard API access. When this
  is off, calls fail in a way that looks like bad credentials — document the
  distinction so it isn't misdiagnosed.
- `Authorization: Bearer <key>`; note the legacy `X-Cisco-Meraki-API-Key` header
  and that it is not what this skill sends.
- The four bootstrap calls and what each resolves.
- Rate limit: 10 req/sec per org, token bucket, `429` + `Retry-After`.
- Why redirects need a method-preserving handler (Meraki may `308` to a shard
  host; `urllib` otherwise downgrades `POST`→`GET` and can drop `Authorization`).
- `X-Request-Id` — always quote it when reporting a failure to Meraki support.

`references/inventory-and-status.md`
- `GET /organizations/{orgId}/inventory/devices` vs `GET /organizations/{orgId}/devices`
- `GET /organizations/{orgId}/devices/statuses` — `online`/`offline`/`alerting`/`dormant`
- `GET /organizations/{orgId}/devices/availabilities`
- `GET /organizations/{orgId}/devices/uplinksLossAndLatency`
- Licensing: **detect the model first**. Co-termination orgs answer on
  `GET /organizations/{orgId}/licenses/overview`; per-device orgs answer on
  `GET /organizations/{orgId}/licenses`. Calling the wrong one returns a `400`
  that reads like a permissions problem. Document how to tell them apart.

`references/appliance-mx.md`
- VLANs: `GET/PUT /networks/{netId}/appliance/vlans` and `.../vlans/{vlanId}`
  (per-VLAN PUT is safer than the collection).
- L3 firewall: `GET/PUT /networks/{netId}/appliance/firewall/l3FirewallRules`,
  `{"rules": [...]}`, full replacement, plus the implicit default rule trap.
- L7 firewall: `.../firewall/l7FirewallRules`
- Static routes, site-to-site VPN (`.../vpn/siteToSiteVpn` — carries PSKs),
  content filtering, traffic shaping, uplink settings.
- Rule field reference: `comment`, `policy`, `protocol`, `srcCidr`, `srcPort`,
  `destCidr`, `destPort`, `syslogEnabled`.

`references/switch-ms.md`
- `GET /devices/{serial}/switch/ports`, `GET /devices/{serial}/switch/ports/statuses`
- `PUT /devices/{serial}/switch/ports/{portId}` — per-port, so safer than a collection PUT
- `POST /devices/{serial}/switch/ports/cycle` — disruptive; confirm the port list first
- ACLs: `GET/PUT /networks/{netId}/switch/accessControlLists` — full replacement
- STP, QoS rules, stacks, L3 routing interfaces, DHCP relay
- Note Catalyst (`C9`) models are reachable through the same switch endpoints

`references/wireless-mr.md`
- SSIDs: `GET/PUT /networks/{netId}/wireless/ssids/{number}` — per-SSID, safer
- RF profiles, `GET/PUT /devices/{serial}/wireless/radio/settings`
- `GET /networks/{netId}/wireless/clients/connectionStats`
- `GET /networks/{netId}/wireless/latencyStats`
- `GET /networks/{netId}/wireless/channelUtilizationHistory`
- RADIUS-bearing SSID config carries secrets — redacted in diffs, intact in snapshots

`references/logs-and-events.md`
- `GET /networks/{netId}/events` — **requires `productType` on combined
  networks**; returns `pageStartAt`, `pageEndAt`, `events`; uses
  `startingAfter`/`endingBefore` rather than page numbers.
- `GET /organizations/{orgId}/configurationChanges` — fields `ts`, `adminName`,
  `adminEmail`, `networkName`, `page`, `label`, `oldValue`, `newValue`. Up to
  365 days. This is the audit trail for "what broke since Friday".
- `GET /organizations/{orgId}/appliance/security/events` and the per-network form.
- `GET /networks/{netId}/wireless/airMarshal`.
- `GET /organizations/{orgId}/apiRequests` — self-audit of API usage.
- Per-endpoint timespan ceilings and why they are validated client-side.

`references/live-tools.md`
- The create-then-poll pattern: `POST /devices/{serial}/liveTools/{tool}` returns
  a job id; `GET /devices/{serial}/liveTools/{tool}/{id}` until `status` is
  `complete` or `failed`.
- Per-tool platform support table matching `LIVE_TOOLS` in `meraki_client.py`.
- Which tools need which licensing, and that job ids remain pollable after a
  client-side timeout.

`references/change-safety.md`
- Full-replacement PUT semantics, with a worked example of the accident.
- The implicit default rule: `GET` returns it, `PUT` rejects it. Strip on read,
  re-derive on write. **Do not "fix" this by passing it through.**
- Why the diff is positional: reordering a deny above a permit changes behavior
  with identical set membership, so a set-based diff would report "no change".
- Snapshot layout (`{"path", "captured", "payload"}`) and how rollback re-PUTs it.
- Action batches: `confirmed:false` staging as a real server-side dry run;
  `synchronous` vs async; 100 actions; 5 pending batches; atomicity as the reason
  to prefer batches over a loop of PUTs.
- The hard-block list and why each entry is unrecoverable by snapshot.
- Secret handling: redacted in displayed diffs, intact in snapshots, directory
  gitignored.
- Note that the official `meraki` Python SDK is deliberately not used, because it
  hides the HTTP layer the write gate inspects.

- [ ] **Step 4: Confirm the skill's structure matches the authoring standard**

Run:

```bash
ls skills/cisco-meraki skills/cisco-meraki/references skills/cisco-meraki/scripts
head -3 skills/cisco-meraki/SKILL.md
grep -rn "MERAKI_DASHBOARD_API_KEY" skills/cisco-meraki/SKILL.md
```

Expected: no nested `cisco-meraki/cisco-meraki/`; `SKILL.md` line 2 reads
`name: cisco-meraki`; 8 files under `references/`; 4 under `scripts/`.

- [ ] **Step 5: Confirm no secrets or real identifiers leaked into the docs**

Run:

```bash
grep -rnE "Q2[A-Z0-9]{2}-[A-Z0-9]{4}-[A-Z0-9]{4}" skills/cisco-meraki/ | grep -v "Q2XX-1111-1111" | grep -v "Q2XX-2222-2222" | grep -v "Q2XX-9999-9999"
grep -rniE "(api[_-]?key|bearer)\s*[:=]\s*['\"][A-Za-z0-9]{20,}" skills/cisco-meraki/
```

Expected: both produce no output.

- [ ] **Step 6: Commit**

```bash
git add skills/cisco-meraki/SKILL.md skills/cisco-meraki/references
git commit -m "docs(meraki): SKILL.md and eight reference documents"
```

---

### Task 9: Repo registration

**Files:**
- Modify: `skills/README.md` (add one table row)
- Modify: `.claude-plugin/marketplace.json` (add one plugin entry)
- Modify: `CHANGELOG.md` (add an `Unreleased` entry)

**Interfaces:**
- Consumes: the completed skill directory from Tasks 1–8
- Produces: nothing consumed by later tasks (final task)

- [ ] **Step 1: Add the skills/README.md row**

In `skills/README.md`, insert this row in the Overview table, alphabetically
between the `checkpoint-email` and `cloudflare` rows:

```markdown
| [`cisco-meraki`](cisco-meraki) | Cloud / Networking | Cisco Meraki Dashboard API v1 for a single org — inventory and device status, event and config-change logs, security/IDS events, Air Marshal, live diagnostics, and MX/MS/MR config changes gated behind snapshot → diff → confirm with rollback. | Automatic |
```

- [ ] **Step 2: Add the marketplace.json plugin entry**

In `.claude-plugin/marketplace.json`, add to the `plugins` array, keeping
alphabetical order (after the `checkpoint-email` entry):

```json
    {
      "name": "cisco-meraki",
      "source": "./skills/cisco-meraki",
      "description": "Cisco Meraki Dashboard API v1 - inventory, status, event and config-change logs, live diagnostics, and MX/MS/MR config changes with snapshot/diff/confirm and rollback.",
      "version": "1.0.0"
    },
```

- [ ] **Step 3: Verify the JSON is still valid**

Run: `python -c "import json; d=json.load(open('.claude-plugin/marketplace.json')); names=[p['name'] for p in d['plugins']]; assert 'cisco-meraki' in names, names; assert len(names)==len(set(names)), 'duplicate plugin name'; print('ok:', len(names), 'plugins')"`

Expected: `ok: 12 plugins`

- [ ] **Step 4: Add the CHANGELOG entry**

In `CHANGELOG.md`, replace the `## [Unreleased]` section's `Nothing yet.` line
with:

```markdown
### Added

- `skills/cisco-meraki` — Cisco Meraki Dashboard API v1 skill for a single
  organization, covering MX/MS/MR. Reads inventory, device status, the network
  event log, the org configuration change log, MX security/IDS events, and Air
  Marshal; runs live diagnostics (ping, cable test, throughput, ARP/MAC table,
  wake-on-LAN); and makes configuration changes behind a snapshot → diff →
  confirm gate with single-command rollback. Bulk changes route through staged
  Action Batches so Meraki validates the payload server-side before commit.
  Stdlib-only Python, no pip install. Includes the repo's first unit test suite
  (`python -m unittest discover -s skills/cisco-meraki/tests -p "test_*.py"`).
```

- [ ] **Step 5: Run the full test suite one final time**

Run: `python -m unittest discover -s skills/cisco-meraki/tests -p "test_*.py"`

Expected: `OK (skipped=4)` — 106 tests ran, 102 passed, 4 live-smoke tests skipped
because `MERAKI_LIVE_TEST` is unset. 0 failures, 0 errors.

- [ ] **Step 6: Confirm nothing untracked or ignored got staged**

Run: `git status --short && git check-ignore -v .meraki-snapshots/ 2>/dev/null || echo "WARNING: .meraki-snapshots not ignored"`

Expected: no `.meraki-snapshots/` in `git status`; `check-ignore` confirms the
`.gitignore` rule matches.

- [ ] **Step 7: Commit**

```bash
git add skills/README.md .claude-plugin/marketplace.json CHANGELOG.md
git commit -m "chore(meraki): register cisco-meraki skill in README, marketplace, and changelog"
```

---

## Self-Review

**Spec coverage** — every spec section maps to a task:

| Spec section | Task |
|---|---|
| 2 Environment / stdlib-only / single org | Global Constraints, Tasks 1–2 |
| 3 Directory layout | File Structure (with documented 2→4 script deviation) |
| 4 Frontmatter + symptom triggers | Task 8 Step 1 |
| 5 Bootstrap sequence + cache | Task 2 |
| 6 Authentication model | Task 1 (env-only key), Task 8 (`auth-and-bootstrap.md`) |
| 7 Read path, pagination, timespans, live tools, redirects, 429, errors | Tasks 1, 2, 3, 4 |
| 8 Write path, semantic diff, default rule, action batches | Tasks 5, 6, 7 |
| 9 Safety rails: snapshot, diff-not-count, hard blocks, redaction | Task 6 (blocks, snapshot, confirm), Task 5 (redaction) |
| 10 Reference map | Task 8 Step 3 |
| 11 Runbooks | Task 8 Step 3 — distributed across the reference files whose endpoints each runbook uses, rather than a separate file |
| 12 Testing (7 named cases + live smoke) | Tasks 1–7 cover all 7; **see gap below** |
| 13 Verify against live API | Task 8 `references/*`; inline `# Verify against the live API` comments in Tasks 4 and 7 |
| 14 Repo registration | Task 9 |

**Gap found and closed:** spec section 12 requires a read-only live smoke test
gated behind an env var. No task provided it. Add to Task 8 as a new step before
Step 6:

- [ ] **Task 8, Step 5b: Add the live smoke test**

Create `skills/cisco-meraki/tests/test_live_smoke.py`:

```python
"""Read-only live smoke test. Skipped unless MERAKI_LIVE_TEST=1 and a key is set.

Never writes. Never asserts on tenant-specific values.
"""
import os
import unittest

import context  # noqa: F401

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
```

Run: `python -m unittest discover -s skills/cisco-meraki/tests -p "test_live_smoke.py" -v`
Expected without the env vars: `OK (skipped=4)`

**Placeholder scan:** no `TBD`, `TODO`, "implement later", or "similar to Task N".
Every code step carries complete code. Task 8 Step 3 specifies required content
per reference file rather than full prose — acceptable because those are
documentation files whose exact wording is not load-bearing, and each bullet names
the concrete endpoints and behaviors to document.

**Type consistency check:** `MerakiHTTP.request` returns `(data, headers)`
everywhere it is called (Tasks 2, 3, 4, 6, 7 all unpack two values).
`diff_rules` returns `list[tuple[str, int, dict]]` in Task 5 and is consumed with
that shape in Task 6's `render_diff` call and its assertions. `extract_rules` /
`strip_default_rule` / `_repack` compose consistently in `ConfigTool.apply`.
`check_hard_block(method, path)` has the same signature in Tasks 6 and 7.
`ConfigTool.resolve_org` is defined in Task 7 and used only there. Test helper
`http_with` returns `(http, calls)` in every test module, though the `calls` tuple
is 2-wide in Tasks 2–3 and 3-wide (including body) in Tasks 4, 6, 7 — intentional,
and each module defines its own helper, so there is no cross-module conflict.
