"""server_settings: the Bridge's view of config.yaml, defaults and fallbacks."""

import test_server_harness as h

import pytest

from config_loader import (
    DEFAULT_HISTORY_DAYS,
    DEFAULT_MAX_MESSAGE_BYTES,
    DEFAULT_SERVER_HOST,
    server_settings,
)
from server.roles import token_sha256

ALICE_HASH = token_sha256(h.ALICE_TOKEN)


def test_defaults_when_sections_missing():
    settings = server_settings({"bridge": {"port": 9999}})
    assert settings.host == DEFAULT_SERVER_HOST == "127.0.0.1"
    assert settings.port == 9999
    assert settings.history_days == DEFAULT_HISTORY_DAYS == 14
    assert settings.peer_token_sha256 == {}
    assert settings.shared_token is None
    assert settings.allow_shared_token is False
    assert settings.max_message_bytes == DEFAULT_MAX_MESSAGE_BYTES == 64 * 1024
    assert settings.rate_per_second == 10
    assert settings.max_stored_per_peer > 0


def test_bridge_host_is_not_used_as_bind_address():
    # bridge.host is the clients' target; an old 0.0.0.0 must not keep the
    # Bridge listening on every interface
    settings = server_settings({"bridge": {"host": "0.0.0.0", "port": 1}})
    assert settings.host == "127.0.0.1"


def test_explicit_values_win():
    settings = server_settings({
        "server": {
            "host": "0.0.0.0", "port": 7000, "history_days": 30,
            "max_message_bytes": 1000, "rate_per_second": 2, "rate_burst": 4, "max_stored_per_peer": 50,
        },
        "auth": {"peers": {h.ALICE: ALICE_HASH}, "token": "legacy", "allow_shared_token": True},
        "bridge": {"port": 9999, "history_days": 180},
    })
    assert (settings.host, settings.port, settings.history_days) == ("0.0.0.0", 7000, 30)
    assert settings.peer_token_sha256 == {h.ALICE: ALICE_HASH}
    assert settings.shared_token == "legacy"
    assert settings.allow_shared_token is True
    assert (settings.max_message_bytes, settings.rate_per_second, settings.rate_burst) == (1000, 2, 4)
    assert settings.max_stored_per_peer == 50


def test_empty_yaml_sections_are_tolerated():
    # "auth:" with nothing under it loads as None
    settings = server_settings({"auth": None, "server": None, "bridge": {"port": 1}})
    assert settings.peer_token_sha256 == {}


def test_observer_and_user_hashes_fall_back_to_bridge_section():
    settings = server_settings({"bridge": {"port": 1, "observer_token_sha256": "o", "user_token_sha256": "u"}})
    assert (settings.observer_token_sha256, settings.user_token_sha256) == ("o", "u")
    settings = server_settings({
        "bridge": {"port": 1, "observer_token_sha256": "o"},
        "auth": {"observer_token_sha256": "new"},
    })
    assert settings.observer_token_sha256 == "new"


def test_bridge_token_is_not_the_legacy_shared_token():
    # The contract names auth.token; bridge.token is what clients send
    assert server_settings({"bridge": {"port": 1, "token": "x"}}).shared_token is None


def test_history_days_falls_back_to_bridge_section():
    assert server_settings({"bridge": {"port": 1, "history_days": 180}}).history_days == 180


@pytest.mark.parametrize(
    "server",
    [{"history_days": 0}, {"max_message_bytes": 0}, {"rate_per_second": -1}, {"port": "x"}, {"rate_burst": 0}],
)
def test_invalid_numbers_rejected(server):
    with pytest.raises(ValueError):
        server_settings({"server": {"port": 1, **server}})


def test_peers_must_be_a_mapping():
    with pytest.raises(ValueError, match="auth.peers"):
        server_settings({"server": {"port": 1}, "auth": {"peers": ["a"]}})


def test_port_required_somewhere():
    with pytest.raises(ValueError, match="port"):
        server_settings({})
