"""Shared fixtures for the Meraki skill's tests.

http_with() fakes the injectable _send seam on MerakiHTTP, so no test ever
opens a socket. `calls` always records (method, url, body) -- tests that don't
care about the body simply ignore the third element.
"""
import json

# `context` puts scripts/ on sys.path as an import side effect.
import context  # noqa: F401  # pylint: disable=unused-import

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
