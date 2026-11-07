"""The ai-connect CLI (ai_connect_cli.py) and its launcher, against tmp configs and a real loopback Bridge.

Must-block: a token on stdout or stderr (only its last 4 show), a join code
that pins a certificate redeemed over plain ws:// (fail closed), a used code,
an identity overwritten without --force, any change in a --dry-run. Must-allow:
invite -> join -> connect; token -> join --token-file; revoke; list; status.
"""

import asyncio
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest
import yaml

import test_server_harness  # noqa: F401  # pylint: disable=unused-import  # puts the repo root on sys.path first

import ai_connect_cli as cli  # noqa: E402
import installer  # noqa: E402
import join_codes as jc  # noqa: E402
from config_loader import client_settings, server_settings  # noqa: E402
from server.main import build_server  # noqa: E402
from test_server_harness import connect, register  # noqa: E402

PLUGIN = Path(__file__).resolve().parents[1]
TOKEN_RE = re.compile(r"[0-9a-f]{64}")


@pytest.fixture
def bridge_config(tmp_path):
    path = tmp_path / "bridge" / "config.yaml"
    path.parent.mkdir()
    config = installer._example()  # pylint: disable=protected-access
    config["server"]["port"] = 0
    config["server"]["host"] = "127.0.0.1"
    config["client"]["bridge_url"] = "ws://127.0.0.1:9999"
    jc.write_config(path, config)
    return path


@pytest.fixture
def laptop_config(tmp_path):
    return tmp_path / "laptop" / "config.yaml"


def ai(capsys, config, *argv):
    code = cli.main(["--config", str(config), *argv])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def snapshot(directory: Path) -> dict:
    return {p.relative_to(directory).as_posix(): p.read_bytes() for p in directory.rglob("*") if p.is_file()}


class LiveBridge:
    """The Bridge on a loopback port in a thread, so the CLI's blocking calls can reach it."""

    def __init__(self, config_path, tmp_path):
        settings = server_settings(yaml.safe_load(config_path.read_text(encoding="utf-8")))
        self.server = build_server(settings, db_path=str(tmp_path / "m.db"), config_path=config_path)
        self.server.reload_seconds = 0.05
        self.loop = asyncio.new_event_loop()
        self.ready = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.server.start())
        self.ready.set()
        self.loop.run_forever()

    def __enter__(self):
        self.thread.start()
        assert self.ready.wait(10)
        return self

    def call(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(10)

    def __exit__(self, *exc):
        self.call(self.server.stop())
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(10)

    @property
    def port(self):
        return self.server.bound_port


async def try_register(port, token, name):
    async with connect(type("S", (), {"bound_port": port})(), token) as ws:
        return await register(ws, name)


# --- invite and join ----------------------------------------------------------------

def test_invite_then_join_then_connect(bridge_config, laptop_config, capsys, tmp_path):
    with LiveBridge(bridge_config, tmp_path) as bridge:
        code, out, err = ai(capsys, bridge_config, "bridge", "invite", "--name", "laptop",
                            "--host", "127.0.0.1", "--port", str(bridge.port))
        assert code == 0, err
        join_code = re.search(r"^  ([A-Z2-7]{5}(?:-[A-Z2-7]{1,5})+)$", out, re.M).group(1)

        code, out, err = ai(capsys, laptop_config, "join", join_code)
        assert code == 0, err
        assert not TOKEN_RE.search(out + err)
        laptop = yaml.safe_load(laptop_config.read_text(encoding="utf-8"))
        token = laptop["client"]["token"]
        assert f"****{token[-4:]}" in out
        assert laptop["client"]["name"] == "laptop"
        assert laptop["client"]["bridge_url"] == f"ws://127.0.0.1:{bridge.port}"
        client_settings(laptop)  # the client reads what join wrote
        assert bridge.call(try_register(bridge.port, token, "laptop"))["type"] == "registered"

        # The same code a second time: refused, and the laptop's identity is untouched
        code, _out, err = ai(capsys, laptop_config, "join", join_code, "--force")
        assert code == 1 and jc.GENERIC_REFUSAL in err
        assert yaml.safe_load(laptop_config.read_text(encoding="utf-8"))["client"]["token"] == token


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits")
def test_join_writes_the_config_owner_only(bridge_config, laptop_config, capsys, tmp_path):
    with LiveBridge(bridge_config, tmp_path) as bridge:
        text = jc.create_invite(bridge_config, "laptop", 3600, "127.0.0.1", bridge.port)
        assert ai(capsys, laptop_config, "join", text)[0] == 0
    assert laptop_config.stat().st_mode & 0o077 == 0


def test_code_that_pins_a_certificate_fails_closed(laptop_config, capsys):
    text = jc.encode(jc.JoinCode("127.0.0.1", 9, b"\x01" * 32, b"s" * 16, "laptop", 4_000_000_000))
    code, _out, err = ai(capsys, laptop_config, "join", text)
    assert code == 1 and "TLS" in err
    assert not laptop_config.exists()


def test_expired_code_is_refused_before_the_network(laptop_config, capsys):
    text = jc.encode(jc.JoinCode("127.0.0.1", 9, jc.NO_FINGERPRINT, b"s" * 16, "laptop", 1000))
    code, _out, err = ai(capsys, laptop_config, "join", text)
    assert code == 1 and "expired" in err


def test_mistyped_code_is_a_usage_error(laptop_config, capsys):
    code, _out, err = ai(capsys, laptop_config, "join", "AAAAA-BBBBB")
    assert code == 2 and "join code" in err


def test_join_will_not_replace_an_identity_without_force(laptop_config, capsys):
    config = installer._example()  # pylint: disable=protected-access
    config["client"]["token"] = "f" * 64
    jc.write_config(laptop_config, config)
    text = jc.encode(jc.JoinCode("127.0.0.1", 9, jc.NO_FINGERPRINT, b"s" * 16, "laptop", 4_000_000_000))
    code, out, err = ai(capsys, laptop_config, "join", text)
    assert code == 2 and "--force" in err
    assert "f" * 64 not in out + err


def test_invite_refuses_a_loopback_only_address(bridge_config, capsys):
    code, _out, err = ai(capsys, bridge_config, "bridge", "invite", "--name", "laptop")
    assert code == 2 and "--host" in err


def test_invite_out_writes_the_code_to_a_file_not_stdout(bridge_config, capsys, tmp_path):
    target = tmp_path / "code.txt"
    code, out, _err = ai(capsys, bridge_config, "bridge", "invite", "--name", "laptop", "--host", "100.64.0.1",
                         "--port", "9999", "--out", str(target))
    assert code == 0
    text = target.read_text(encoding="utf-8").strip()
    assert jc.decode(text).name == "laptop" and text not in out


# --- token, revoke, list, status -----------------------------------------------------

def test_token_join_with_token_file_and_revoke_disconnects(bridge_config, laptop_config, capsys, tmp_path):
    with LiveBridge(bridge_config, tmp_path) as bridge:
        code, out, err = ai(capsys, bridge_config, "bridge", "token", "--name", "desk")
        assert code == 0, err
        issued = bridge_config.parent / cli.ISSUED_DIR / "desk.token"
        token = issued.read_text(encoding="utf-8").strip()
        assert token not in out + err and f"****{token[-4:]}" in out
        enrolled = yaml.safe_load(bridge_config.read_text(encoding="utf-8"))["auth"]["peers"]
        assert jc.sha256_hex(token) == enrolled["desk"]

        code, out, err = ai(capsys, laptop_config, "join", "--token-file", str(issued),
                            "--bridge", f"127.0.0.1:{bridge.port}", "--name", "desk")
        assert code == 0, err
        assert token not in out + err

        async def connected_then_revoked():
            await asyncio.sleep(0.4)  # a few auth polls: the Bridge takes the new token in by itself
            async with connect(type("S", (), {"bound_port": bridge.port})(), token) as ws:
                assert (await register(ws, "desk"))["type"] == "registered"
                await asyncio.to_thread(cli.main, ["--config", str(bridge_config), "bridge", "revoke", "--name",
                                                   "desk"])
                try:
                    while True:
                        await asyncio.wait_for(ws.recv(), 5)
                except Exception as err:  # pylint: disable=broad-exception-caught
                    return getattr(getattr(err, "rcvd", None), "code", repr(err))

        assert bridge.call(connected_then_revoked()) == 1008
        assert not issued.exists()
        assert "desk" not in yaml.safe_load(bridge_config.read_text(encoding="utf-8"))["auth"]["peers"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits")
def test_issued_token_file_is_owner_only(bridge_config, capsys):
    assert ai(capsys, bridge_config, "bridge", "token", "--name", "desk")[0] == 0
    assert (bridge_config.parent / cli.ISSUED_DIR / "desk.token").stat().st_mode & 0o077 == 0


def test_revoke_unknown_peer_fails(bridge_config, capsys):
    code, _out, err = ai(capsys, bridge_config, "bridge", "revoke", "--name", "ghost")
    assert code == 1 and "no such peer" in err


def test_revoke_ends_a_pending_code(bridge_config, capsys):
    text = jc.create_invite(bridge_config, "laptop", 3600, "127.0.0.1", 9999)
    assert ai(capsys, bridge_config, "bridge", "revoke", "--name", "laptop")[0] == 0
    with pytest.raises(jc.Refused):
        jc.redeem(bridge_config, jc.decode(text).secret, "laptop")


def test_list_shows_peers_and_codes_never_hashes(bridge_config, capsys):
    ai(capsys, bridge_config, "bridge", "token", "--name", "desk")
    jc.create_invite(bridge_config, "laptop", 3600, "127.0.0.1", 9999)
    code, out, _err = ai(capsys, bridge_config, "bridge", "list")
    assert code == 0
    assert "desk" in out and "laptop: pending" in out
    assert not TOKEN_RE.search(out)


def test_status_masks_the_token(bridge_config, capsys):
    ai(capsys, bridge_config, "bridge", "token", "--name", "desk")
    config = yaml.safe_load(bridge_config.read_text(encoding="utf-8"))
    config["client"]["token"] = "e" * 60 + "1234"
    jc.write_config(bridge_config, config)
    code, out, _err = ai(capsys, bridge_config, "status", "--offline")
    assert code == 0 and "****1234" in out and "e" * 60 not in out
    assert "1 peer(s) enrolled" in out


def test_status_without_config_fails(tmp_path, capsys):
    assert ai(capsys, tmp_path / "none.yaml", "status")[0] == 1


# --- dry run --------------------------------------------------------------------------

@pytest.mark.parametrize("argv", [
    ["bridge", "invite", "--name", "laptop", "--host", "100.64.0.1", "--port", "9999", "--dry-run"],
    ["bridge", "token", "--name", "desk", "--dry-run"],
    ["bridge", "revoke", "--name", "desk", "--dry-run"],
    ["join", "--dry-run"],
])
def test_dry_run_changes_nothing(bridge_config, capsys, argv):
    before = snapshot(bridge_config.parent)
    code, out, _err = ai(capsys, bridge_config, *argv)
    assert code == 0 and "would:" in out
    assert snapshot(bridge_config.parent) == before


# --- the launcher ---------------------------------------------------------------------

@pytest.mark.skipif(shutil.which("sh") is None, reason="needs a POSIX sh")
def test_launcher_fails_loudly_without_python(tmp_path):
    """No python3/python/py on PATH and no venv: stderr says so and the exit is 127, never 0."""
    launcher = tmp_path / "plugin" / "bin" / "ai-connect"
    launcher.parent.mkdir(parents=True)
    shutil.copy(PLUGIN / "bin" / "ai-connect", launcher)
    sh = shutil.which("sh")
    empty = tmp_path / "emptybin"
    empty.mkdir()
    # The launcher uses shell built-ins only until it has a Python, so an empty PATH is enough
    result = subprocess.run([sh, launcher.as_posix(), "status"], capture_output=True, text=True,
                            env={"PATH": str(empty), "HOME": str(tmp_path)}, check=False)
    assert result.returncode == 127, result
    assert "no Python 3.10 or newer found" in result.stderr


@pytest.mark.skipif(shutil.which("sh") is None, reason="needs a POSIX sh")
def test_launcher_runs_the_cli_with_a_python(tmp_path):
    """With a Python on PATH the launcher reaches ai_connect_cli: its exit and output are the CLI's."""
    shim = tmp_path / "pybin"
    shim.mkdir()
    (shim / "python3").write_text(f'#!/bin/sh\nexec "{Path(sys.executable).as_posix()}" "$@"\n',
                                  encoding="utf-8", newline="\n")
    (shim / "python3").chmod(0o755)
    env = {**os.environ, "PATH": str(shim) + os.pathsep + os.environ.get("PATH", "")}
    result = subprocess.run([shutil.which("sh"), (PLUGIN / "bin" / "ai-connect").as_posix(), "--config",
                             str(tmp_path / "none.yaml"), "status"],
                            capture_output=True, text=True, check=False, cwd=str(tmp_path), env=env)
    assert result.returncode == 1 and "config: missing" in result.stdout, result
