"""acl-template.hujson: parses, and grants peers the Bridge's TCP 9999 and nothing else."""
import json
import re
from pathlib import Path

import pytest

ACL = Path(__file__).resolve().parent.parent / "acl-template.hujson"


def load_hujson(text: str) -> dict:
    text = re.sub(r"^\s*//.*$", "", text, flags=re.M)  # full-line comments only
    text = re.sub(r",(\s*[}\]])", r"\1", text)  # trailing commas
    return json.loads(text)


@pytest.fixture(scope="module")
def policy():
    return load_hujson(ACL.read_text(encoding="utf-8"))


def test_tags_have_owners(policy):
    assert set(policy["tagOwners"]) == {"tag:ai-peer", "tag:bridge"}


def test_peer_grants_are_only_bridge_tcp_9999(policy):
    peer_grants = [g for g in policy["grants"] if "tag:ai-peer" in g["src"]]
    assert peer_grants == [{"src": ["tag:ai-peer"], "dst": ["tag:bridge"], "ip": ["tcp:9999"]}]


def test_nothing_grants_access_to_peers(policy):
    for grant in policy["grants"]:
        assert "tag:ai-peer" not in grant["dst"]
        assert "*" not in grant["dst"]
    assert "acls" not in policy


def test_policy_tests_assert_allow_and_deny(policy):
    accepts = {(t["src"], t["proto"], a) for t in policy["tests"] for a in t.get("accept", [])}
    denies = {(t["src"], t["proto"], d) for t in policy["tests"] for d in t.get("deny", [])}
    assert ("tag:ai-peer", "tcp", "tag:bridge:9999") in accepts
    assert ("tag:ai-peer", "tcp", "tag:ai-peer:9999") in denies  # no peer-to-peer
    assert ("tag:ai-peer", "tcp", "tag:bridge:22") in denies  # only the one port
    assert ("tag:ai-peer", "udp", "tag:bridge:9999") in denies  # tcp only
