"""Roles: per-peer tokens bound to names, the legacy shared token, reserved names."""

import test_server_harness as h

import pytest

from server.roles import OBSERVER, PEER, USER, Roles, token_sha256


def bearer(token: str) -> str:
    return f"Bearer {token}"


def test_per_peer_token_maps_to_its_bound_name():
    identity = h.make_roles().identity_for(bearer(h.ALICE_TOKEN))
    assert identity is not None
    assert identity.role == PEER
    assert identity.peer_name == h.ALICE
    assert not identity.shared


def test_observer_and_user_tokens_keep_their_roles():
    roles = h.make_roles()
    assert roles.identity_for(bearer(h.OBSERVER_TOKEN)).role == OBSERVER
    assert roles.identity_for(bearer(h.USER_TOKEN)).role == USER


@pytest.mark.parametrize("header", ["", "Bearer ", "Basic abc", "Bearer wrong-token", h.ALICE_TOKEN])
def test_unknown_or_malformed_header_has_no_identity(header):
    assert h.make_roles().identity_for(header) is None


def test_shared_token_refused_by_default():
    roles = h.make_roles()
    assert roles.identity_for(bearer(h.SHARED_TOKEN)) is None
    assert roles.refusal_reason(bearer(h.SHARED_TOKEN)) == "shared_token_disabled"


def test_shared_token_accepted_when_allowed():
    identity = h.make_roles(allow_shared_token=True).identity_for(bearer(h.SHARED_TOKEN))
    assert identity is not None
    assert identity.role == PEER
    assert identity.shared
    assert identity.peer_name is None


@pytest.mark.parametrize(
    ("header", "reason"),
    [("", "missing_token"), ("Basic x", "missing_token"), ("Bearer nope", "unknown_token")],
)
def test_refusal_reasons(header, reason):
    assert h.make_roles().refusal_reason(header) == reason


def test_register_refusals():
    roles = h.make_roles(allow_shared_token=True)
    alice = roles.identity_for(bearer(h.ALICE_TOKEN))
    shared = roles.identity_for(bearer(h.SHARED_TOKEN))
    assert roles.register_refusal(alice, h.ALICE) is None
    assert roles.register_refusal(alice, h.BOB) == "name_not_bound_to_token"
    # A shared token must not take a name that has its own token
    assert roles.register_refusal(shared, h.BOB) == "name_bound_to_other_token"
    assert roles.register_refusal(shared, "Other:Project") is None


@pytest.mark.parametrize("name", ["Bridge", "bridge", "BRIDGE", "User:max", "user:max", "USER:"])
def test_reserved_names_refused_even_for_shared(name):
    roles = h.make_roles(allow_shared_token=True)
    shared = roles.identity_for(bearer(h.SHARED_TOKEN))
    assert roles.register_refusal(shared, name) == "reserved_name"


def test_watch_only_own_name_with_per_peer_token():
    roles = h.make_roles()
    alice = roles.identity_for(bearer(h.ALICE_TOKEN))
    assert roles.watch_refusal(alice, h.ALICE) is None
    assert roles.watch_refusal(alice, h.BOB) == "watch_not_own_name"
    assert roles.watch_refusal(alice, "User:max") == "reserved_name"


@pytest.mark.parametrize("name", ["Bridge", "User:x"])
def test_reserved_name_in_auth_peers_is_a_config_error(name):
    with pytest.raises(ValueError, match="reserved"):
        Roles(peer_token_sha256={name: token_sha256("x")})


@pytest.mark.parametrize("digest", ["", "abc", "z" * 64, token_sha256("x") + "0"])
def test_malformed_peer_hash_is_a_config_error(digest):
    with pytest.raises(ValueError, match="SHA-256"):
        Roles(peer_token_sha256={h.ALICE: digest})


def test_uppercase_hash_accepted():
    roles = Roles(peer_token_sha256={h.ALICE: token_sha256(h.ALICE_TOKEN).upper()})
    assert roles.identity_for(bearer(h.ALICE_TOKEN)).peer_name == h.ALICE


def test_one_token_for_two_names_is_a_config_error():
    digest = token_sha256("same")
    with pytest.raises(ValueError, match="more than one"):
        Roles(peer_token_sha256={h.ALICE: digest, h.BOB: digest})


def test_unicode_token_hashes():
    roles = Roles(peer_token_sha256={h.ALICE: token_sha256("tökén-✓")})
    assert roles.identity_for(bearer("tökén-✓")).peer_name == h.ALICE
