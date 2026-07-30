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
