"""TLS with a pinned certificate fingerprint (bridge_tls.py, 0.2.15): every test uses tmp directories only.

Must-block: a certificate whose SHA-256 is not the pinned one (the token is
never sent, nothing retries, over wss:// or ws://); a config that pairs a pin
with ws:// (downgrade) or wss:// with no pin; a plain listener once
server.tls.required is set; a private key readable by group or other; an old
pin after rotation. Must-allow: the pinned certificate connects; ws:// and
wss:// both serve during the transition release; rotation re-pins this
machine's own client.
"""

import asyncio
import datetime
import os
import socket
import ssl

import pytest
import websockets
import yaml

import test_server_harness  # noqa: F401  # pylint: disable=unused-import  # puts the repo root on sys.path first

import ai_connect_cli as cli  # noqa: E402
import bridge_tls  # noqa: E402
import config_loader  # noqa: E402
import installer  # noqa: E402
import join_codes as jc  # noqa: E402
from client import bridge_client  # noqa: E402
from config_loader import client_settings, server_settings  # noqa: E402
from server.main import build_server  # noqa: E402
from server.roles import token_sha256  # noqa: E402
from test_server_harness import register  # noqa: E402

TOKEN = "laptop-token-" + "0" * 40
NAME = "laptop"


@pytest.fixture
def config_path(tmp_path):
    path = tmp_path / "bridge" / "config.yaml"
    path.parent.mkdir()
    config = installer._example()  # pylint: disable=protected-access
    config["server"].update(host="127.0.0.1", port=0)
    config["auth"]["peers"] = {NAME: token_sha256(TOKEN)}
    config["client"]["bridge_url"] = "ws://127.0.0.1:9999"
    jc.write_config(path, config)
    return path


def settings_of(config_path):
    return server_settings(yaml.safe_load(config_path.read_text(encoding="utf-8")))


async def started(config_path, tmp_path):
    server = build_server(settings_of(config_path), db_path=str(tmp_path / "m.db"), config_path=config_path)
    await server.start()
    return server


def pinned(port, fingerprint, token=TOKEN):
    return websockets.connect(f"wss://127.0.0.1:{port}", additional_headers={"Authorization": f"Bearer {token}"},
                              ssl=bridge_tls.client_context(fingerprint), open_timeout=5)


def plain(port, token=TOKEN):
    return websockets.connect(f"ws://127.0.0.1:{port}", additional_headers={"Authorization": f"Bearer {token}"},
                              open_timeout=5)


# --- the certificate ------------------------------------------------------------------

def test_generate_records_the_sha256_of_the_der(tmp_path):
    info = bridge_tls.generate(tmp_path)
    der = ssl.PEM_cert_to_DER_cert(info.cert_path.read_text(encoding="ascii"))
    assert info.fingerprint == bridge_tls.fingerprint_of_der(der)
    assert bridge_tls.load(tmp_path).fingerprint == info.fingerprint
    days = (info.not_after - info.not_before).days
    assert bridge_tls.DEFAULT_VALIDITY_DAYS <= days <= bridge_tls.DEFAULT_VALIDITY_DAYS + 1


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits; Windows gets an owner-only ACL (tsadmin.private_dir)")
def test_key_is_0600_and_the_directory_0700(tmp_path):
    info = bridge_tls.generate(tmp_path)
    assert info.key_path.stat().st_mode & 0o777 == 0o600
    assert info.key_path.parent.stat().st_mode & 0o777 == 0o700


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits")
def test_a_key_others_can_read_is_refused(tmp_path):
    info = bridge_tls.generate(tmp_path)
    info.key_path.chmod(0o644)
    with pytest.raises(bridge_tls.TlsError, match="not 600"):
        bridge_tls.server_context(info)


def test_ensure_never_replaces_a_certificate(tmp_path):
    first, created = bridge_tls.ensure(tmp_path)
    again, created_again = bridge_tls.ensure(tmp_path)
    assert created and not created_again and again.fingerprint == first.fingerprint


def test_half_a_pair_is_an_error_not_a_new_certificate(tmp_path):
    info = bridge_tls.generate(tmp_path)
    info.key_path.unlink()
    with pytest.raises(bridge_tls.TlsError, match="only one of"):
        bridge_tls.ensure(tmp_path)


@pytest.mark.parametrize("text", ["AB" * 32, "sha256:" + "ab" * 32, ":".join(["AB"] * 32)])
def test_fingerprint_forms(text):
    assert bridge_tls.normalize_fingerprint(text) == "ab" * 32


@pytest.mark.parametrize("text", ["", "ab" * 31, "zz" * 32, "ab" * 33])
def test_bad_fingerprints_are_refused(text):
    with pytest.raises(ValueError):
        bridge_tls.normalize_fingerprint(text)


# --- the pin --------------------------------------------------------------------------

def test_matching_pin_connects_and_mismatch_fails_closed_before_the_token(config_path, tmp_path):
    seen = []

    async def scenario():
        server = build_server(settings_of(config_path), db_path=str(tmp_path / "m.db"), config_path=config_path)
        original = server._check_token  # pylint: disable=protected-access

        async def spy(connection, request):
            seen.append(request.headers.get("Authorization"))
            return await original(connection, request)
        server._check_token = spy  # pylint: disable=protected-access  # before start(): serve() binds it
        await server.start()
        try:
            fingerprint = bridge_tls.load(config_path.parent).fingerprint
            async with pinned(server.tls_bound_port, fingerprint) as ws:
                assert (await register(ws, NAME))["type"] == "registered"
            with pytest.raises(bridge_tls.PinMismatch):
                async with pinned(server.tls_bound_port, "ab" * 32, token="must-never-arrive"):
                    pass
        finally:
            await server.stop()

    asyncio.run(scenario())
    assert seen == [f"Bearer {TOKEN}"]  # the mismatched handshake never reached the HTTP layer


def test_bridge_client_mismatch_stops_and_never_tries_ws(config_path, tmp_path, monkeypatch):
    uris = []
    real_connect = websockets.connect

    def recording(uri, **kwargs):
        uris.append(uri)
        return real_connect(uri, **kwargs)
    monkeypatch.setattr(bridge_client.websockets, "connect", recording)

    async def scenario():
        server = await started(config_path, tmp_path)
        try:
            client = bridge_client.BridgeClient("127.0.0.1", server.tls_bound_port, NAME, TOKEN, fingerprint="ab" * 32)
            assert await client.connect() is False
            assert client.pin_mismatch and not client.connected
            client.start_reconnect()  # refused: a pin mismatch, like a refused token, is not retried
            assert client.reconnecting is False
            assert client._reconnect_task is None  # pylint: disable=protected-access
            good = bridge_client.BridgeClient("127.0.0.1", server.tls_bound_port, NAME, TOKEN,
                                              fingerprint=bridge_tls.load(config_path.parent).fingerprint)
            assert await good.connect() is True
            await good.disconnect()
        finally:
            await server.stop()

    asyncio.run(scenario())
    assert uris and all(uri.startswith("wss://") for uri in uris)


def test_rotation_changes_the_fingerprint_and_old_pins_fail(config_path, tmp_path, capsys):
    old = bridge_tls.ensure(config_path.parent)[0].fingerprint
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["client"].update(bridge_url="wss://127.0.0.1:10000", bridge_fingerprint=old)
    jc.write_config(config_path, config)
    pending = jc.create_invite(config_path, "desk", 3600, "100.64.0.1", 10000, bridge_tls.fingerprint_bytes(old))

    assert cli.main(["--config", str(config_path), "bridge", "cert", "rotate"]) == 0
    out = capsys.readouterr().out
    new = bridge_tls.load(config_path.parent).fingerprint
    assert new != old and new in out and "re-pin" in out
    # This machine's own client follows; the code made for the old certificate is ended
    assert yaml.safe_load(config_path.read_text(encoding="utf-8"))["client"]["bridge_fingerprint"] == new
    with pytest.raises(jc.Refused):
        jc.redeem(config_path, jc.decode(pending).secret, "desk")

    async def scenario():
        server = await started(config_path, tmp_path)
        try:
            with pytest.raises(bridge_tls.PinMismatch):
                async with pinned(server.tls_bound_port, old):
                    pass
            async with pinned(server.tls_bound_port, new) as ws:
                assert (await register(ws, NAME))["type"] == "registered"
        finally:
            await server.stop()

    asyncio.run(scenario())


# --- the listeners --------------------------------------------------------------------

def test_both_listeners_serve_in_the_transition_release(config_path, tmp_path, caplog):
    async def scenario():
        server = await started(config_path, tmp_path)
        try:
            assert server.bound_port != server.tls_bound_port
            async with plain(server.bound_port) as ws:
                assert (await register(ws, NAME))["type"] == "registered"
            fingerprint = bridge_tls.load(config_path.parent).fingerprint
            async with pinned(server.tls_bound_port, fingerprint) as ws:
                assert (await register(ws, NAME))["type"] == "registered"
        finally:
            await server.stop()

    asyncio.run(scenario())
    assert "plaintext_listener" in caplog.text and "plaintext_client" in caplog.text


def test_tls_required_opens_no_plain_listener(config_path, tmp_path):
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    free = socket.socket()
    free.bind(("127.0.0.1", 0))
    plain_port = free.getsockname()[1]
    free.close()
    config["server"].update(port=plain_port, tls={"required": True, "port": 0})
    jc.write_config(config_path, config)

    async def scenario():
        server = await started(config_path, tmp_path)
        try:
            assert server.plain is False
            with pytest.raises(OSError):
                async with plain(plain_port):
                    pass
            async with pinned(server.tls_bound_port, bridge_tls.load(config_path.parent).fingerprint) as ws:
                assert (await register(ws, NAME))["type"] == "registered"
        finally:
            await server.stop()

    asyncio.run(scenario())


# --- the config -----------------------------------------------------------------------

def client_config(url, fingerprint=None):
    client = {"name": NAME, "token": TOKEN, "bridge_url": url}
    if fingerprint is not None:
        client["bridge_fingerprint"] = fingerprint
    return {"client": client}


def test_wss_with_pin_is_tls():
    settings = client_settings(client_config("wss://100.64.0.1:10000", "AB" * 32))
    assert settings.tls and settings.fingerprint == "ab" * 32 and settings.uri == "wss://100.64.0.1:10000"
    assert isinstance(settings.connect_options()["ssl"], ssl.SSLContext)


def test_downgrade_pin_with_ws_is_refused():
    with pytest.raises(ValueError, match="refusing to send the token in clear"):
        client_settings(client_config("ws://100.64.0.1:9999", "ab" * 32))


def test_wss_without_a_pin_is_refused():
    with pytest.raises(ValueError, match="bridge_fingerprint is not set"):
        client_settings(client_config("wss://100.64.0.1:10000"))


def test_plain_ws_still_works_with_one_warning(caplog, monkeypatch):
    monkeypatch.setattr(config_loader, "_warned_plain", False)
    caplog.set_level("WARNING", logger="ai_connect.transport")  # the watcher, if imported, raises it to ERROR
    for _ in range(2):
        settings = client_settings(client_config("ws://100.64.0.1:9999"))
    assert not settings.tls and settings.connect_options() == {}
    assert caplog.text.count("Deprecated since 0.2.15") == 1


def test_server_tls_defaults_and_errors():
    settings = server_settings({"server": {"port": 9999}})
    assert (settings.tls_enabled, settings.tls_port, settings.tls_required) == (True, 10000, False)
    with pytest.raises(ValueError, match="must differ"):
        server_settings({"server": {"port": 9999, "tls": {"port": 9999}}})
    with pytest.raises(ValueError, match="listen on nothing"):
        server_settings({"server": {"port": 9999, "tls": {"enabled": False, "required": True}}})


def test_websockets_refuses_a_context_on_ws():
    """The library's own guard, relied on: an ssl context never travels with a ws:// URI."""
    async def scenario():
        with pytest.raises(ValueError):
            await websockets.connect("ws://127.0.0.1:9", ssl=bridge_tls.client_context("ab" * 32))
    asyncio.run(scenario())


# --- ai-connect pin and cert show -----------------------------------------------------

def test_pin_checks_the_certificate_first(config_path, tmp_path, capsys):
    import threading  # pylint: disable=import-outside-toplevel
    laptop = tmp_path / "laptop.yaml"
    jc.write_config(laptop, client_config("ws://127.0.0.1:9999"))
    loop = asyncio.new_event_loop()
    server = build_server(settings_of(config_path), db_path=str(tmp_path / "m.db"), config_path=config_path)
    ready = threading.Event()

    def run():
        asyncio.set_event_loop(loop)
        loop.run_until_complete(server.start())
        ready.set()
        loop.run_forever()
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    assert ready.wait(10)
    try:
        port = str(server.tls_bound_port)
        before = laptop.read_bytes()
        assert cli.main(["--config", str(laptop), "pin", "ab" * 32, "--port", port]) == 1
        assert "MISMATCH" in capsys.readouterr().err and laptop.read_bytes() == before
        fingerprint = bridge_tls.load(config_path.parent).fingerprint
        assert cli.main(["--config", str(laptop), "pin", fingerprint, "--port", port]) == 0
        assert "matches the pin" in capsys.readouterr().out
        written = yaml.safe_load(laptop.read_text(encoding="utf-8"))["client"]
        assert written["bridge_url"] == f"wss://127.0.0.1:{port}" and written["bridge_fingerprint"] == fingerprint
    finally:
        asyncio.run_coroutine_threadsafe(server.stop(), loop).result(10)
        loop.call_soon_threadsafe(loop.stop)
        thread.join(10)


def test_cert_show_makes_and_prints_the_fingerprint(config_path, capsys):
    assert cli.main(["--config", str(config_path), "bridge", "cert", "show"]) == 0
    out = capsys.readouterr().out
    assert bridge_tls.load(config_path.parent).fingerprint in out
    assert "PRIVATE" not in out


def test_an_expired_certificate_is_still_the_pinned_one_and_said_loudly(config_path, tmp_path, caplog):
    long_ago = datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)
    bridge_tls.generate(config_path.parent, validity_days=1, now=long_ago)

    async def scenario():
        server = await started(config_path, tmp_path)
        try:
            async with pinned(server.tls_bound_port, bridge_tls.load(config_path.parent).fingerprint) as ws:
                assert (await register(ws, NAME))["type"] == "registered"
        finally:
            await server.stop()

    asyncio.run(scenario())
    assert "tls_certificate_expired" in caplog.text
