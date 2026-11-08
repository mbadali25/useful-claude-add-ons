"""The ai-connect CLI (ai_connect_cli.py) and its launcher, against tmp configs and a real loopback Bridge.

Must-block: a token on stdout or stderr (only its last 4 show), a join code
that pins a certificate redeemed over plain ws:// (fail closed), a used code,
an identity overwritten without --force, any change in a --dry-run. Must-allow:
invite -> join -> connect; token -> join --token-file; revoke; list; status.
"""

import asyncio
import json
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


# --- the plain-HTTP join: exposure warning and expiry cap ---------------------------------

EXPOSURE = "the join is plain HTTP"


@pytest.mark.parametrize("host", ["127.0.0.1", "100.64.0.1", "100.127.255.254", "fd7a:115c:a1e0::5",
                                  "bridge.tail1234.ts.net"])
def test_invite_to_loopback_or_tailscale_does_not_warn(bridge_config, capsys, host):
    code, out, err = ai(capsys, bridge_config, "bridge", "invite", "--name", "laptop", "--host", host,
                        "--port", "9999", "--dry-run")
    assert code == 0, err
    assert EXPOSURE not in out + err


@pytest.mark.parametrize("host,why", [
    ("192.168.1.20", "private address"),  # RFC 1918: WireGuard or the LAN at large, cannot tell
    ("10.0.0.5", "private address"),
    ("203.0.113.9", "neither loopback nor a Tailscale address"),  # documentation range: is_private, not LAN
    ("100.128.0.1", "neither loopback nor a Tailscale address"),  # just past 100.64.0.0/10
    ("bridge.example.com", "host name"),  # unknown is not safe
])
def test_invite_to_any_other_address_warns(bridge_config, capsys, host, why):
    code, out, _err = ai(capsys, bridge_config, "bridge", "invite", "--name", "laptop", "--host", host,
                         "--port", "9999", "--dry-run")
    assert code == 0
    assert "WARNING" in out and EXPOSURE in out and why in out


def test_invite_default_expiry_is_one_hour(bridge_config, capsys):
    code, out, _err = ai(capsys, bridge_config, "bridge", "invite", "--name", "laptop", "--host", "100.64.0.1",
                         "--port", "9999")
    assert code == 0 and "expires in 1h" in out
    text = re.search(r"^  ([A-Z2-7]{5}(?:-[A-Z2-7]{1,5})+)$", out, re.M).group(1)
    stored = json_invites(bridge_config)[-1]
    assert stored["expires"] - stored["created"] == 3600 and jc.decode(text).expires == stored["expires"]


@pytest.mark.parametrize("expiry", ["25h", "2d", "7d"])
def test_invite_past_24h_is_refused_without_the_flag(bridge_config, capsys, expiry):
    before = snapshot(bridge_config.parent)
    code, _out, err = ai(capsys, bridge_config, "bridge", "invite", "--name", "laptop", "--host", "100.64.0.1",
                         "--port", "9999", "--expiry", expiry)
    assert code == 2 and "--allow-long-expiry" in err
    assert snapshot(bridge_config.parent) == before


def test_invite_past_24h_with_the_flag_warns(bridge_config, capsys):
    code, out, _err = ai(capsys, bridge_config, "bridge", "invite", "--name", "laptop", "--host", "100.64.0.1",
                         "--port", "9999", "--expiry", "2d", "--allow-long-expiry")
    assert code == 0 and "WARNING: --allow-long-expiry" in out
    stored = json_invites(bridge_config)[-1]
    assert stored["expires"] - stored["created"] == 2 * 86400


def test_invite_24h_needs_no_flag(bridge_config, capsys):
    code, out, _err = ai(capsys, bridge_config, "bridge", "invite", "--name", "laptop", "--host", "100.64.0.1",
                         "--port", "9999", "--expiry", "24h")
    assert code == 0 and "--allow-long-expiry" not in out


def test_invite_help_documents_the_exposure(capsys):
    with pytest.raises(SystemExit):
        cli.main(["bridge", "invite", "--help"])
    text = " ".join(capsys.readouterr().out.split())
    assert "plain HTTP" in text and "X-AI-Connect-Join" in text and "permanent peer token" in text
    assert "--allow-long-expiry" in text and "at most 24h" in text


def test_join_help_ranks_the_command_line_code_weakest(capsys):
    with pytest.raises(SystemExit):
        cli.main(["join", "--help"])
    text = " ".join(capsys.readouterr().out.split())
    assert "weakest" in text and "--code-file" in text and "AI_CONNECT_JOIN_CODE" in text


def json_invites(config_path):
    return json.loads(jc.invites_path(config_path).read_text(encoding="utf-8"))["invites"]


# --- a broken config.yaml: its text never reaches the terminal --------------------------

SECRET_ON_THE_BROKEN_LINE = "9f" * 32
# A snippet can cut a long line short: any 16 characters of the token are a leak
LEAK = SECRET_ON_THE_BROKEN_LINE[:16]


# Read from a file (as the CLI does) PyYAML shows no snippet of the line, but these messages quote the text
@pytest.mark.parametrize("broken", [
    f"auth: {{peers: *{SECRET_ON_THE_BROKEN_LINE}}}\n",  # "found undefined alias '<token>'"
    f"client:\n  token: !{SECRET_ON_THE_BROKEN_LINE} x\n",  # "could not determine a constructor for the tag"
])
@pytest.mark.parametrize("argv", [
    ["status", "--offline"],
    ["bridge", "list"],
    ["bridge", "revoke", "--name", "laptop"],
    ["bridge", "token", "--name", "desk"],
    ["bridge", "invite", "--name", "laptop", "--host", "100.64.0.1", "--port", "9999"],
])
def test_a_yaml_error_shows_its_place_never_the_text(tmp_path, capsys, broken, argv):
    config = tmp_path / "bridge" / "config.yaml"
    config.parent.mkdir()
    config.write_text(broken, encoding="utf-8")
    with pytest.raises(yaml.YAMLError) as raw, open(config, encoding="utf-8") as handle:
        yaml.safe_load(handle)
    assert LEAK in str(raw.value)  # the leak this guards against is real
    code, out, err = ai(capsys, config, *argv)
    assert code == 1
    assert LEAK not in out + err
    assert "not valid YAML (line " in err


def test_the_cli_process_does_not_leak_a_yaml_error_either(tmp_path):
    """The whole process, stdout and stderr: no traceback carries the text past the CLI's own handling."""
    config = tmp_path / "config.yaml"
    config.write_text(f"auth: {{peers: *{SECRET_ON_THE_BROKEN_LINE}}}\n", encoding="utf-8")
    result = subprocess.run([sys.executable, str(PLUGIN / "ai_connect_cli.py"), "--config", str(config),
                             "bridge", "revoke", "--name", "x"], capture_output=True, text=True, check=False)
    assert result.returncode == 1, result
    assert LEAK not in result.stdout + result.stderr


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


# --- the Windows launcher ---------------------------------------------------------------
# bin\ai-connect.cmd once ran the CLI inside ( ) blocks, where cmd expands %ERRORLEVEL% when it reads the
# block, before the CLI runs: every exit was 0. These run the launcher against a stand-in CLI that exits
# with the code it is given, from each of its three Python branches, with LF and CRLF line endings (cmd's
# label search depends on them; the repository stores LF).

FAKE_CLI = "import sys\nprint('fake cli', sys.argv[1:])\nsys.exit(int(sys.argv[1]))\n"
SYSTEM32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
windows_only = pytest.mark.skipif(os.name != "nt", reason="bin\\ai-connect.cmd is cmd.exe's")


def fake_plugin(root: Path, eol: str) -> Path:
    """A plugin tree with the real launcher and a stand-in ai_connect_cli.py; returns the launcher."""
    launcher = root / "bin" / "ai-connect.cmd"
    launcher.parent.mkdir(parents=True, exist_ok=True)
    text = (PLUGIN / "bin" / "ai-connect.cmd").read_text(encoding="utf-8").replace("\r\n", "\n")
    launcher.write_bytes(text.replace("\n", eol).encode("utf-8"))
    (root / "ai_connect_cli.py").write_text(FAKE_CLI, encoding="utf-8")
    return launcher


def run_cmd(launcher: Path, path: list[str], *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PATH": os.pathsep.join(path)}
    return subprocess.run([str(launcher), *args], capture_output=True, text=True, check=False, env=env,
                          cwd=str(launcher.parent))


@pytest.fixture(scope="module")
def venv_python(tmp_path_factory):
    """A real venv (no pip: fast) to stand in for the plugin's own."""
    root = tmp_path_factory.mktemp("venv-plugin")
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(root / "venv")], check=True,
                   capture_output=True)
    return root


@windows_only
@pytest.mark.parametrize("eol", ["\n", "\r\n"], ids=["lf", "crlf"])
@pytest.mark.parametrize("exit_code", [0, 1, 3])
@pytest.mark.parametrize("branch", ["venv", "py", "python"])
def test_cmd_launcher_passes_the_cli_exit_code_through(tmp_path, venv_python, branch, exit_code, eol):
    if branch == "venv":
        launcher = fake_plugin(venv_python, eol)
        path = [SYSTEM32]  # nothing else: only the venv can answer
    elif branch == "py":
        py = shutil.which("py")
        if py is None:
            pytest.skip("no py launcher on this machine")
        launcher = fake_plugin(tmp_path, eol)
        path = [str(Path(py).parent), SYSTEM32]
    else:
        launcher = fake_plugin(tmp_path, eol)
        # Not C:\Windows, where py.exe lives: python is the only candidate
        path = [str(Path(sys.executable).parent), SYSTEM32]
    result = run_cmd(launcher, path, str(exit_code), "two words")
    assert "fake cli" in result.stdout, result
    assert result.returncode == exit_code, result


@windows_only
@pytest.mark.parametrize("eol", ["\n", "\r\n"], ids=["lf", "crlf"])
def test_cmd_launcher_without_python_exits_127(tmp_path, eol):
    launcher = fake_plugin(tmp_path, eol)
    result = run_cmd(launcher, [SYSTEM32], "0")
    assert result.returncode == 127, result
    assert "no Python 3.10 or newer found" in result.stderr
