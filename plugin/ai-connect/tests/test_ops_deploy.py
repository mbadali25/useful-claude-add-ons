"""deploy/deploy.py and its deploy.sh / deploy.ps1 pair, against fakes only.

Every system tool deploy drives (tailscale, sudo, systemctl, ufw, schtasks, netsh,
claude, ...) is tests/fake_deploy_bin.py on a minimal PATH, HOME is a tmp dir,
systemd units go to a tmp dir, and the "venv" is a pip-less venv that sees this
interpreter's packages. A small WebSocket server stands in for the Bridge and
checks the Bearer token the way the real one does. Both OS flavours (systemd +
ufw, scheduled task + netsh) run on any host through AI_CONNECT_DEPLOY_OS.
"""
import asyncio
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
from http import HTTPStatus
from pathlib import Path

import pytest
import yaml

PLUGIN = Path(__file__).resolve().parent.parent
DEPLOY_DIR = PLUGIN / "deploy"
DEPLOY = DEPLOY_DIR / "deploy.py"
FAKE = Path(__file__).resolve().parent / "fake_deploy_bin.py"
TOOLS = ("tailscale", "sudo", "tee", "rm", "systemctl", "ufw", "schtasks", "netsh", "claude")
SUBNET = "100.64.0.0/10"
AUTH_KEY = "tskey-auth-kDEPLOY123-AuthKeyMaterialThatMustNotLeak0123"
PEER_TOKEN = "f00dfacecafe" * 5 + "beef"
# Calls that change something; a rerun or a dry run must make none of them
MUTATING = {("tee",), ("rm",), ("systemctl", "enable"), ("systemctl", "restart"), ("systemctl", "disable"),
            ("systemctl", "daemon-reload"), ("ufw", "allow"), ("ufw", "delete"), ("schtasks", "/Create"),
            ("schtasks", "/Run"), ("schtasks", "/End"), ("schtasks", "/Delete"), ("netsh", "advfirewall", "firewall", "add"),
            ("netsh", "advfirewall", "firewall", "delete"), ("claude", "plugin", "install"),
            ("claude", "plugin", "uninstall"), ("claude", "mcp", "add"), ("claude", "mcp", "remove"),
            ("tailscale", "up")}

PWSH_CANDIDATES = [r"C:\Program Files\PowerShell\7\pwsh.exe", "/usr/bin/pwsh", "/usr/local/bin/pwsh",
                   "/opt/homebrew/bin/pwsh"]
PWSH = next((p for p in PWSH_CANDIDATES if os.path.isfile(p)), None)
GIT_BASH = r"C:\Program Files\Git\bin\bash.exe"
BASH = GIT_BASH if os.name == "nt" and os.path.isfile(GIT_BASH) else (None if os.name == "nt" else shutil.which("bash"))


# ---------------------------------------------------------------- fixtures


@pytest.fixture(scope="session")
def venv(tmp_path_factory):
    """A venv without pip whose site-packages point at this interpreter's: deps import, nothing installs."""
    path = tmp_path_factory.mktemp("deploy-venv") / "venv"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(path)], check=True,
                   stdin=subprocess.DEVNULL, capture_output=True)
    python = next(p for p in (path / "Scripts" / "python.exe", path / "bin" / "python") if p.is_file())
    purelib = subprocess.run([str(python), "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
                             check=True, capture_output=True, text=True, stdin=subprocess.DEVNULL).stdout.strip()
    dirs = [p for p in sys.path if p and os.path.isdir(p) and Path(p).resolve() != PLUGIN.resolve()]
    Path(purelib, "outer.pth").write_text("\n".join(dirs) + "\n", encoding="utf-8")
    return path


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FakeBridge:
    """Accepts a WebSocket whose Bearer token hashes to one of accepted(), refuses 401 otherwise."""

    def __init__(self, accepted):
        self.accepted = accepted
        self.port = free_port()
        self.loop = asyncio.new_event_loop()
        self.ready = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        assert self.ready.wait(10), "fake Bridge did not start"

    def _run(self):
        import websockets  # pylint: disable=import-outside-toplevel

        def check(connection, request):
            token = request.headers.get("Authorization", "").removeprefix("Bearer ")
            if hashlib.sha256(token.encode()).hexdigest() in self.accepted():
                return None
            return connection.respond(HTTPStatus.UNAUTHORIZED, "Missing or wrong AI-Connect token\n")

        async def handler(ws):
            await ws.wait_closed()

        async def main():
            self.stop = asyncio.Event()  # pylint: disable=attribute-defined-outside-init
            async with websockets.serve(handler, "127.0.0.1", self.port, process_request=check):
                self.ready.set()
                await self.stop.wait()

        self.loop.run_until_complete(main())

    def close(self):
        self.loop.call_soon_threadsafe(self.stop.set)
        self.thread.join(10)


class Box:
    """One fake machine: HOME, PATH of fakes, fake state, and how to run deploy on it."""

    def __init__(self, tmp_path: Path, venv: Path, target: str):
        self.tmp = tmp_path
        self.home = tmp_path / "home"
        self.home.mkdir()
        self.systemd = tmp_path / "systemd"
        self.systemd.mkdir()
        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        self.state_file = tmp_path / "fake-state.json"
        self.log = tmp_path / "fake-log.jsonl"
        self.log.write_text("", encoding="utf-8")
        self.set(ts_ip="127.0.0.1", ts_backend="Running")
        for name in TOOLS:
            self.add_tool(name)
        pydir = str(Path(sys.executable).parent)
        sysdirs = [r"C:\Windows\System32", r"C:\Windows"] if os.name == "nt" else ["/usr/bin", "/bin"]
        self.env = {k: v for k, v in os.environ.items()
                    if k not in ("TS_AUTHKEY", "TS_AUTHKEY_FILE", "AI_CONNECT_BRIDGE_HOST", "AI_CONNECT_PEER_TOKEN",
                                 "AI_CONNECT_INSTALLER", "PYTHONPATH")}
        self.env.update(HOME=str(self.home), USERPROFILE=str(self.home), PATH=os.pathsep.join([str(self.bin), pydir, *sysdirs]),
                        FAKE_DEPLOY_STATE=str(self.state_file), FAKE_DEPLOY_LOG=str(self.log),
                        AI_CONNECT_VENV=str(venv), AI_CONNECT_SYSTEMD_DIR=str(self.systemd),
                        AI_CONNECT_TS_STATE_DIR=str(tmp_path / "ts-state"), AI_CONNECT_DEPLOY_OS=target,
                        AI_CONNECT_DEPLOY_HEALTH_WAIT="3", AI_CONNECT_TSD_WAIT="0",
                        XDG_CACHE_HOME=str(tmp_path / "xdg-cache"), PYTHONIOENCODING="utf-8")
        self.target = target

    def add_tool(self, name: str) -> None:
        if os.name == "nt":
            (self.bin / f"{name}.cmd").write_text(f'@"{sys.executable}" "{FAKE}" {name} %*\r\n', encoding="utf-8")
        else:
            path = self.bin / name
            path.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" {name} "$@"\n', encoding="utf-8", newline="\n")
            path.chmod(0o755)

    def remove_tool(self, name: str) -> None:
        for path in self.bin.glob(f"{name}*"):
            path.unlink()

    def set(self, **values) -> None:
        state = self.state() if self.state_file.exists() else {}
        state.update(values)
        self.state_file.write_text(json.dumps(state), encoding="utf-8")

    def state(self) -> dict:
        return json.loads(self.state_file.read_text(encoding="utf-8"))

    def calls(self) -> list[list[str]]:
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines() if line]

    def mutations(self) -> list[list[str]]:
        return [c for c in self.calls() if any(tuple(c[:len(m)]) == m for m in MUTATING)]

    def clear_log(self) -> None:
        self.log.write_text("", encoding="utf-8")

    @property
    def config_file(self) -> Path:
        return self.home / ".config" / "ai-connect" / "config.yaml"

    def config(self) -> dict:
        return yaml.safe_load(self.config_file.read_text(encoding="utf-8"))

    def deploy(self, *args: str, extra_env: dict | None = None) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(DEPLOY), *args], capture_output=True, text=True, check=False,
                              stdin=subprocess.DEVNULL, env=dict(self.env, **(extra_env or {})), timeout=180)

    def snapshot(self) -> dict:
        """Every file under the fake machine's HOME and systemd dir, with its bytes."""
        return {str(p): p.read_bytes() for root in (self.home, self.systemd) for p in sorted(root.rglob("*"))
                if p.is_file()}


@pytest.fixture(params=["linux", "windows"])
def box(request, tmp_path, venv):
    return Box(tmp_path, venv, request.param)


@pytest.fixture
def bridge_server(box):
    """A Bridge that accepts the peers the box's own config lists (the real Bridge's rule)."""
    def accepted():
        if not box.config_file.exists():
            return set()
        return set(((box.config().get("auth") or {}).get("peers") or {}).values())
    server = FakeBridge(accepted)
    yield server
    server.close()


def output(res: subprocess.CompletedProcess) -> str:
    return res.stdout + res.stderr


def deploy_bridge(box, server, *extra):
    return box.deploy("bridge", "--name", "hub", "--peer", "laptop", "--port", str(server.port), *extra)


def steps(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("[")]


# ---------------------------------------------------------------- bridge


def test_bridge_happy_path(box, bridge_server):
    res = deploy_bridge(box, bridge_server)
    assert res.returncode == 0, output(res)
    assert [s.split("]")[0] for s in steps(res.stdout)] == [f"[{n}/6" for n in range(1, 7)]
    config = box.config()
    assert config["server"]["host"] == "127.0.0.1"
    assert config["server"]["port"] == bridge_server.port
    assert config["client"]["bridge_url"] == f"ws://127.0.0.1:{bridge_server.port}"
    assert set(config["auth"]["peers"]) == {"hub", "laptop"}
    token_file = box.home / ".config" / "ai-connect" / "peer-tokens" / "laptop.token"
    token = token_file.read_text(encoding="utf-8").strip()
    assert hashlib.sha256(token.encode()).hexdigest() == config["auth"]["peers"]["laptop"]
    assert "accepted this machine's token" in res.stdout
    state = box.state()
    if box.target == "linux":
        unit = (box.systemd / "ai-connect.service").read_text(encoding="utf-8")
        assert "-m server.main" in unit and f"WorkingDirectory={PLUGIN}" in unit
        assert state["units"]["ai-connect"] == {"active": True, "enabled": True}
        assert any(SUBNET in line and str(bridge_server.port) in line for line in state["ufw"])
    else:
        assert state["tasks"]["AI-Connect Bridge"] == "Running"
        assert state["rules"]["AI-Connect Bridge"] == SUBNET
        assert "pythonw.exe" in state["task_xml"] and "LeastPrivilege" in state["task_xml"]
        assert any("profile=private" in c for c in box.calls() if c[:5] == ["netsh", "advfirewall", "firewall", "add", "rule"])


def test_bridge_rerun_is_idempotent(box, bridge_server):
    assert deploy_bridge(box, bridge_server).returncode == 0
    before = box.snapshot()
    box.clear_log()
    res = deploy_bridge(box, bridge_server)
    assert res.returncode == 0, output(res)
    assert box.mutations() == []
    assert box.snapshot() == before
    already = [line for line in res.stdout.splitlines() if "already done" in line]
    assert len(already) == 5, res.stdout  # deps, config, peer, service, firewall; health always checks
    assert "would:" not in res.stdout


def test_bridge_dry_run_changes_nothing(box, bridge_server):
    before = box.snapshot()
    state = box.state()
    res = deploy_bridge(box, bridge_server, "--dry-run")
    assert res.returncode == 0, output(res)
    assert "(dry run)" in res.stdout and "would:" in res.stdout
    assert box.mutations() == []
    assert box.snapshot() == before
    assert box.state() == state
    assert not box.config_file.exists()


def test_bridge_dry_run_after_deploy_reports_already_done(box, bridge_server):
    assert deploy_bridge(box, bridge_server).returncode == 0
    box.clear_log()
    res = deploy_bridge(box, bridge_server, "--dry-run")
    assert res.returncode == 0, output(res)
    assert "would:" not in res.stdout.replace("would: connect", "")
    assert box.mutations() == []


def test_bridge_never_prints_a_token(box, bridge_server):
    first = deploy_bridge(box, bridge_server)
    second = deploy_bridge(box, bridge_server)
    status = box.deploy("status")
    secrets = [(box.home / ".config" / "ai-connect" / "peer-tokens" / "laptop.token").read_text(encoding="utf-8").strip(),
               box.config()["client"]["token"]]
    for name in ("observer.token", "user.token"):
        secrets.append((box.home / ".config" / "ai-connect" / name).read_text(encoding="utf-8").strip())
    text = output(first) + output(second) + output(status)
    for secret in secrets:
        assert len(secret) == 64
        assert not any(secret[i:i + 12] in text for i in range(len(secret) - 11)), "a token leaked"
    assert "****" in first.stdout  # the new peer's token is shown masked


def test_bridge_new_peer_on_rerun_restarts_service(box, bridge_server):
    assert deploy_bridge(box, bridge_server).returncode == 0
    box.clear_log()
    res = deploy_bridge(box, bridge_server, "--peer", "desk")
    assert res.returncode == 0, output(res)
    assert "desk" in box.config()["auth"]["peers"]
    restart = ["systemctl", "restart", "ai-connect"] if box.target == "linux" else ["schtasks", "/Run", "/TN", "AI-Connect Bridge"]
    assert any(c[-len(restart):] == restart or c[:len(restart)] == restart for c in box.calls()), box.calls()


def test_bridge_without_tailscale_ip_fails(box, bridge_server):
    box.set(ts_ip="")
    res = deploy_bridge(box, bridge_server)
    assert res.returncode == 1
    assert "no Tailscale IPv4 address" in res.stderr
    assert not box.config_file.exists()


def test_bridge_without_tailscale_installed(box, bridge_server):
    box.remove_tool("tailscale")
    if shutil.which("tailscale", path=box.env["PATH"]):
        pytest.skip("a real tailscale is on the minimal PATH")
    res = deploy_bridge(box, bridge_server)
    assert res.returncode == 3, output(res)
    assert "tailscale is not installed" in res.stderr


def test_bridge_health_check_fails_when_bridge_refuses(box):
    server = FakeBridge(set)  # refuses every token
    try:
        res = box.deploy("bridge", "--name", "hub", "--port", str(server.port))
    finally:
        server.close()
    assert res.returncode == 1
    assert "refused this machine's token" in res.stderr


# ---------------------------------------------------------------- peer


@pytest.fixture
def peer_setup(box, tmp_path):
    box.set(ts_backend="Stopped", ts_ip="")
    token_file = tmp_path / "laptop.token"
    token_file.write_text(PEER_TOKEN + "\n", encoding="utf-8")
    server = FakeBridge(lambda: {hashlib.sha256(PEER_TOKEN.encode()).hexdigest()})
    yield box, server, token_file
    server.close()


def deploy_peer(box, server, token_file, *extra):
    return box.deploy("peer", "--name", "laptop", "--bridge", "127.0.0.1", "--port", str(server.port),
                      "--token-file", str(token_file), *extra, extra_env={"TS_AUTHKEY": AUTH_KEY})


def test_peer_happy_path(peer_setup):
    box, server, token_file = peer_setup
    res = deploy_peer(box, server, token_file)
    assert res.returncode == 0, output(res)
    assert [s.split("]")[0] for s in steps(res.stdout)] == [f"[{n}/5" for n in range(1, 6)]
    state = box.state()
    assert state["plugins"] == ["ai-connect@useful-claude-add-ons"]
    assert str(PLUGIN / "client" / "server.py") in state["mcp"]["ai-connect"]
    assert state["ts_backend"] == "Running"
    up = [c for c in box.calls() if c[:2] == ["tailscale", "up"]]
    assert len(up) == 1 and "--hostname=laptop" in up[0]
    client = box.config()["client"]
    assert client == {**client, "name": "laptop", "token": PEER_TOKEN, "bridge_url": f"ws://127.0.0.1:{server.port}"}
    assert "accepted this machine's token" in res.stdout


def test_peer_rerun_is_idempotent(peer_setup):
    box, server, token_file = peer_setup
    assert deploy_peer(box, server, token_file).returncode == 0
    before = box.snapshot()
    box.clear_log()
    res = deploy_peer(box, server, token_file)
    assert res.returncode == 0, output(res)
    assert box.mutations() == []
    assert box.snapshot() == before
    assert len([line for line in res.stdout.splitlines() if "already done" in line]) == 5, res.stdout


def test_peer_dry_run_changes_nothing(peer_setup):
    box, server, token_file = peer_setup
    before, state = box.snapshot(), box.state()
    res = deploy_peer(box, server, token_file, "--dry-run")
    assert res.returncode == 0, output(res)
    assert "would:" in res.stdout
    assert box.mutations() == []
    assert box.snapshot() == before and box.state() == state


def test_peer_never_prints_token_or_auth_key(peer_setup):
    box, server, token_file = peer_setup
    text = output(deploy_peer(box, server, token_file, "--dry-run")) + output(deploy_peer(box, server, token_file))
    text += output(deploy_peer(box, server, token_file)) + output(box.deploy("status"))
    for secret in (PEER_TOKEN, AUTH_KEY):
        assert not any(secret[i:i + 12] in text for i in range(len(secret) - 11)), "a secret leaked"
    assert "****beef" in text


def test_peer_wrong_token_fails_verification(peer_setup, tmp_path):
    box, server, _ = peer_setup
    wrong = tmp_path / "wrong.token"
    wrong.write_text("0123456789abcdef" * 4, encoding="utf-8")
    res = deploy_peer(box, server, wrong)
    assert res.returncode == 1
    assert "refused this machine's token" in res.stderr


def test_peer_without_auth_key_when_off_tailnet_fails(peer_setup):
    box, server, token_file = peer_setup
    res = box.deploy("peer", "--name", "laptop", "--bridge", "127.0.0.1", "--port", str(server.port),
                     "--token-file", str(token_file))
    assert res.returncode == 1
    assert "no auth key" in res.stderr


# ---------------------------------------------------------------- bad args, status, uninstall


@pytest.mark.parametrize("args", [
    [], ["bogus"], ["peer", "--bridge", "127.0.0.1"], ["peer", "--name", "laptop"],
    ["peer", "--name", "bad name!", "--bridge", "127.0.0.1"], ["peer", "--name", "laptop", "--bridge", "a b"],
    ["peer", "--name", "laptop", "--bridge", "127.0.0.1"], ["bridge", "--port", "70000"],
    ["bridge", "--vpn-subnet", "nope"], ["bridge", "--peer", "-x-"], ["uninstall"], ["status", "--dry-run"],
], ids=lambda a: " ".join(a) or "no-args")
def test_bad_arguments_exit_2_and_change_nothing(box, args):
    before, state = box.snapshot(), box.state()
    res = box.deploy(*args)
    assert res.returncode == 2, output(res)
    assert box.mutations() == [] and box.snapshot() == before and box.state() == state


def test_status_reports_a_deployed_bridge(box, bridge_server):
    assert deploy_bridge(box, bridge_server).returncode == 0
    box.clear_log()
    res = box.deploy("status")
    assert res.returncode == 0, output(res)
    assert "service: running" in res.stdout
    assert "firewall: rule present" in res.stdout
    assert "bridge: ok" in res.stdout
    assert box.mutations() == []


def test_uninstall_removes_and_reruns_clean(box, bridge_server):
    assert deploy_bridge(box, bridge_server).returncode == 0
    assert box.deploy("uninstall", "--yes", "--port", str(bridge_server.port), "--dry-run").returncode == 0
    assert box.config_file.exists()
    res = box.deploy("uninstall", "--yes", "--purge", "--port", str(bridge_server.port))
    assert res.returncode == 0, output(res)
    state = box.state()
    assert not box.config_file.exists()
    if box.target == "linux":
        assert not (box.systemd / "ai-connect.service").exists()
        assert state["ufw"] == []
    else:
        assert state["tasks"] == {} and state["rules"] == {}
    box.clear_log()
    again = box.deploy("uninstall", "--yes", "--purge", "--port", str(bridge_server.port))
    assert again.returncode == 0, output(again)
    assert box.mutations() == []
    assert "would:" not in again.stdout and "done: " not in again.stdout.replace("already done: ", "")


def test_uninstall_dry_run_changes_nothing(box, bridge_server):
    assert deploy_bridge(box, bridge_server).returncode == 0
    before, state = box.snapshot(), box.state()
    box.clear_log()
    res = box.deploy("uninstall", "--purge", "--dry-run", "--port", str(bridge_server.port))
    assert res.returncode == 0, output(res)
    assert "would:" in res.stdout
    assert box.mutations() == [] and box.snapshot() == before and box.state() == state


# ---------------------------------------------------------------- the .sh / .ps1 pair


def test_shims_are_lf_and_paired():
    for name in ("deploy.sh", "deploy.ps1", "deploy.py", "config_tool.py"):
        assert b"\r" not in (DEPLOY_DIR / name).read_bytes(), name


def _sh(box, args):
    env = dict(box.env)
    if os.name == "nt":  # Git Bash needs its own coreutils (dirname) on PATH
        env["PATH"] = os.pathsep.join([r"C:\Program Files\Git\usr\bin", env["PATH"]])
    return subprocess.run([BASH, str(DEPLOY_DIR / "deploy.sh"), *args], capture_output=True, text=True,
                          check=False, stdin=subprocess.DEVNULL, env=env, timeout=180)


def _ps1(box, args, tmp_path):
    return subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-File", str(DEPLOY_DIR / "deploy.ps1"), *args],
                          capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL, timeout=180,
                          env=dict(box.env, XDG_CACHE_HOME=str(tmp_path / "xdg-cache")))


@pytest.mark.skipif(not BASH or not PWSH, reason="needs both bash and pwsh at known paths")
def test_sh_and_ps1_print_the_same_steps(box, bridge_server, tmp_path):
    cases = [["bridge", "--name", "hub", "--peer", "laptop", "--port", str(bridge_server.port), "--dry-run"],
             ["uninstall", "--dry-run"], ["status"], ["peer", "--name", "bad name!", "--bridge", "x"]]
    for args in cases:
        sh, ps1 = _sh(box, args), _ps1(box, args, tmp_path)
        assert (sh.returncode, sh.stdout, sh.stderr) == (ps1.returncode, ps1.stdout, ps1.stderr), args
    bridge = _sh(box, cases[0])
    assert steps(bridge.stdout) and steps(bridge.stdout) == steps(box.deploy(*cases[0]).stdout)
    assert box.mutations() == []


@pytest.mark.skipif(not BASH, reason="bash not found")
def test_deploy_sh_syntax():
    res = subprocess.run([BASH, "-n", str(DEPLOY_DIR / "deploy.sh")], capture_output=True, text=True, check=False,
                         stdin=subprocess.DEVNULL)
    assert res.returncode == 0, res.stderr


@pytest.mark.skipif(not PWSH, reason="pwsh not found at an absolute path")
def test_deploy_ps1_passes_the_repo_powershell_static_check(tmp_path):
    checker = PLUGIN.parents[1] / "scripts" / "check-powershell.ps1"
    res = subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-File", str(checker), "-Path",
                          str(DEPLOY_DIR / "deploy.ps1")], capture_output=True, text=True, check=False,
                         stdin=subprocess.DEVNULL, env=dict(os.environ, XDG_CACHE_HOME=str(tmp_path / "xdg-cache")))
    assert res.returncode == 0, res.stdout + res.stderr
