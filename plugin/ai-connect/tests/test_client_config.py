"""client_settings: this machine's peer identity, kept apart from the Bridge's auth:."""

import logging

import pytest

from config_loader import client_settings, server_settings

TOKEN = "c" * 64


def test_client_section_is_read():
    settings = client_settings({
        "client": {"name": "laptop", "token": TOKEN, "bridge_url": "ws://100.64.0.1:9999", "project_dir": "/src"},
    })
    assert (settings.name, settings.token, settings.host, settings.port) == ("laptop", TOKEN, "100.64.0.1", 9999)
    assert settings.project_dir == "/src"
    assert settings.uri == "ws://100.64.0.1:9999"


def test_client_token_is_not_auth_token():
    # A Bridge and its own peer share one config.yaml: auth.token is the
    # Bridge's legacy shared secret, never what this peer sends
    with pytest.raises(ValueError, match="client.token"):
        client_settings({"auth": {"token": TOKEN}, "client": {"bridge_url": "ws://h:1"}})
    settings = client_settings({"auth": {"token": "shared"}, "client": {"token": TOKEN, "bridge_url": "ws://h:1"}})
    assert settings.token == TOKEN


def test_listen_all_bridge_url_connects_to_loopback():
    assert client_settings({"client": {"token": TOKEN, "bridge_url": "ws://0.0.0.0:9"}}).host == "127.0.0.1"


def test_ipv6_bridge_url_keeps_brackets_in_uri():
    settings = client_settings({"client": {"token": TOKEN, "bridge_url": "ws://[fd7a::1]:9"}})
    assert settings.uri == "ws://[fd7a::1]:9"


@pytest.mark.parametrize("url", ["", "http://h:1", "ws://h", "ws://:1", "ws://h:notaport", "h:1"])
def test_bad_bridge_url_rejected(url):
    with pytest.raises(ValueError, match="bridge_url"):
        client_settings({"client": {"token": TOKEN, "bridge_url": url}})


def test_defaults_for_name_and_project_dir():
    settings = client_settings({"client": {"token": TOKEN, "bridge_url": "ws://h:1", "name": None}})
    assert (settings.name, settings.project_dir) == ("", "")


def test_legacy_bridge_section_is_mapped_with_a_warning(caplog):
    config = {"bridge": {"host": "10.0.0.1", "port": 9999, "token": TOKEN}, "peer": {"name": "old"}}
    with caplog.at_level(logging.WARNING):
        settings = client_settings(config)
    assert (settings.name, settings.token, settings.uri) == ("old", TOKEN, "ws://10.0.0.1:9999")
    assert "deprecated" in caplog.text
    assert TOKEN not in caplog.text


def test_server_bridge_fallbacks_warn(caplog):
    with caplog.at_level(logging.WARNING):
        settings = server_settings({"bridge": {"port": 1, "history_days": 3}})
    assert (settings.port, settings.history_days) == (1, 3)
    assert "bridge.port is deprecated" in caplog.text
    assert "bridge.history_days is deprecated" in caplog.text


def test_server_section_does_not_warn(caplog):
    with caplog.at_level(logging.WARNING):
        server_settings({"server": {"port": 1}, "bridge": {"port": 2}})
    assert "deprecated" not in caplog.text


def test_peer_name_prefers_env_then_client_name(tmp_path):
    from peer_name import peer_name

    assert peer_name({"AI_CONNECT_PEER_NAME": "env"}, tmp_path, "laptop") == "env"
    # client.name is the machine; each session adds its project (tests/test_client_sessions.py)
    assert peer_name({}, tmp_path / "proj", "laptop") == "laptop:proj"
    assert peer_name({}, tmp_path / "proj", "").endswith(":proj")


def test_name_taken_is_retried_on_standby_only_once(caplog):
    import asyncio
    import sys
    from pathlib import Path

    client_dir = str(Path(__file__).resolve().parents[1] / "client")
    if client_dir not in sys.path:
        sys.path.append(client_dir)  # last, so client/server.py shadows nothing
    from bridge_client import BridgeClient  # pylint: disable=import-error

    sent = []
    client = BridgeClient("h", 1, "laptop", TOKEN)

    async def fake_send(data):
        sent.append(data)
        return True

    client._send = fake_send
    taken = {"type": "error", "code": "name_taken", "error": "held"}
    with caplog.at_level(logging.WARNING):
        asyncio.run(client._handle(taken))
        asyncio.run(client._handle(taken))
    assert sent == [{"type": "register", "name": "laptop", "standby": True}]
    assert client.standby and not client.connected
    assert "not retrying" in caplog.text
