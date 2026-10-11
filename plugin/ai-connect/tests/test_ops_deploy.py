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
from types import SimpleNamespace

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
            ("schtasks", "/Run"), ("schtasks", "/End"), ("schtasks", "/Delete"),
            ("netsh", "advfirewall", "firewall", "add"), ("netsh", "advfirewall", "firewall", "delete"),
            ("claude", "plugin", "install"),
            ("claude", "plugin", "uninstall"), ("claude", "mcp", "add"), ("claude", "mcp", "remove"),
            ("tailscale", "up")}

PWSH_CANDIDATES = [r"C:\Program Files\PowerShell\7\pwsh.exe", "/usr/bin/pwsh", "/usr/local/bin/pwsh",
                   "/opt/homebrew/bin/pwsh"]
PWSH = next((p for p in PWSH_CANDIDATES if os.path.isfile(p)), None)
GIT_BASH = r"C:\Program Files\Git\bin\bash.exe"
BASH = (GIT_BASH if os.path.isfile(GIT_BASH) else None) if os.name == "nt" else shutil.which("bash")


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
        self.env.update(HOME=str(self.home), USERPROFILE=str(self.home),
                        PATH=os.pathsep.join([str(self.bin), pydir, *sysdirs]),
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
            path.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" {name} "$@"\n', encoding="utf-8",
                            newline="\n")
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


NATIVE = "windows" if os.name == "nt" else "linux"


@pytest.fixture
def box(tmp_path, venv):
    return Box(tmp_path, venv, NATIVE)


def output(res: subprocess.CompletedProcess) -> str:
    return res.stdout + res.stderr


def steps(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("[")]


def leaks(secret: str, text: str) -> bool:
    """True when any 12-character run of the secret shows up in text."""
    return any(secret[i:i + 12] in text for i in range(len(secret) - 11))


def already(res: subprocess.CompletedProcess) -> list[str]:
    return [line for line in res.stdout.splitlines() if "already done" in line]


class Phase:
    """One deploy run on a Box, with what it changed."""

    def __init__(self, box: Box, *args: str, extra_env: dict | None = None):
        before, state = box.snapshot(), box.state()
        box.clear_log()
        self.res = box.deploy(*args, extra_env=extra_env)
        self.calls = box.calls()
        self.mutations = box.mutations()
        self.files_changed = box.snapshot() != before
        self.state_changed = box.state() != state
        self.out = self.res.stdout
        self.text = output(self.res)

    def changed_nothing(self) -> bool:
        return not (self.mutations or self.files_changed or self.state_changed)


# ---------------------------------------------------------------- bridge


@pytest.fixture(scope="module", params=["linux", "windows"])
def bridge(request, tmp_path_factory, venv):
    """A Bridge machine's whole life, run once per OS flavour: each test reads one phase of it.

    dry run on a clean machine -> deploy -> the same again -> status -> add a peer ->
    uninstall dry run -> uninstall -> uninstall again.
    """
    box = Box(tmp_path_factory.mktemp(f"bridge-{request.param}"), venv, request.param)

    def accepted():  # the real Bridge's rule: the hashes in its own auth.peers
        if not box.config_file.exists():
            return set()
        return set(((box.config().get("auth") or {}).get("peers") or {}).values())
    server = FakeBridge(accepted)
    args = ["bridge", "--name", "hub", "--peer", "laptop", "--port", str(server.port)]
    port = ["--port", str(server.port)]
    run = SimpleNamespace()
    run.box, run.port, run.target = box, server.port, request.param
    try:
        run.dry = Phase(box, *args, "--dry-run")
        run.dry_left_config = box.config_file.exists()
        run.first = Phase(box, *args)
        run.config = box.config()
        run.state = box.state()
        run.unit = box.systemd / "ai-connect.service"
        run.unit_text = run.unit.read_text(encoding="utf-8") if run.unit.exists() else ""
        config_dir = box.home / ".config" / "ai-connect"
        run.laptop_token = (config_dir / "peer-tokens" / "laptop.token").read_text(encoding="utf-8").strip()
        run.secrets = [run.laptop_token, run.config["client"]["token"],
                       (config_dir / "observer.token").read_text(encoding="utf-8").strip(),
                       (config_dir / "user.token").read_text(encoding="utf-8").strip()]
        run.second = Phase(box, *args)
        run.status = Phase(box, "status")
        run.add_peer = Phase(box, *args, "--peer", "desk")
        run.peers_after_add = set(box.config()["auth"]["peers"])
        run.uninstall_dry = Phase(box, "uninstall", "--purge", "--dry-run", *port)
        run.uninstall = Phase(box, "uninstall", "--yes", "--purge", *port)
        run.state_after_uninstall = box.state()
        run.config_after_uninstall = box.config_file.exists()
        run.unit_after_uninstall = run.unit.exists()
        run.uninstall_again = Phase(box, "uninstall", "--yes", "--purge", *port)
    finally:
        server.close()
    return run


def test_bridge_happy_path(bridge):
    first = bridge.first
    assert first.res.returncode == 0, first.text
    assert [s.split("]")[0] for s in steps(first.out)] == [f"[{n}/6" for n in range(1, 7)]
    config = bridge.config
    assert config["server"]["host"] == "127.0.0.1"
    assert config["server"]["port"] == bridge.port
    assert config["client"]["bridge_url"] == f"ws://127.0.0.1:{bridge.port}"
    assert set(config["auth"]["peers"]) == {"hub", "laptop"}
    assert hashlib.sha256(bridge.laptop_token.encode()).hexdigest() == config["auth"]["peers"]["laptop"]
    assert "accepted this machine's token" in first.out
    state = bridge.state
    if bridge.target == "linux":
        assert "-m server.main" in bridge.unit_text and f"WorkingDirectory={PLUGIN}" in bridge.unit_text
        assert state["units"]["ai-connect"] == {"active": True, "enabled": True}
        assert any(SUBNET in line and str(bridge.port) in line for line in state["ufw"])
    else:
        assert state["tasks"]["AI-Connect Bridge"] == "Running"
        assert state["rules"]["AI-Connect Bridge"] == SUBNET
        assert "pythonw.exe" in state["task_xml"] and "LeastPrivilege" in state["task_xml"]
        added = [c for c in first.calls if c[:5] == ["netsh", "advfirewall", "firewall", "add", "rule"]]
        assert len(added) == 1 and "profile=private" in added[0] and f"remoteip={SUBNET}" in added[0]


def test_bridge_rerun_is_idempotent(bridge):
    second = bridge.second
    assert second.res.returncode == 0, second.text
    assert second.mutations == []
    assert not second.files_changed and not second.state_changed
    # deps, config, peer, service, firewall; the health check always runs
    assert len(already(second.res)) == 5, second.out
    assert "would:" not in second.out and "  done: write" not in second.out


def test_bridge_dry_run_changes_nothing(bridge):
    dry = bridge.dry
    assert dry.res.returncode == 0, dry.text
    assert "(dry run)" in dry.out and dry.out.count("would:") >= 6, dry.out
    assert dry.changed_nothing(), dry.mutations
    assert not bridge.dry_left_config


def test_bridge_never_prints_a_token(bridge):
    text = "".join(p.text for p in (bridge.dry, bridge.first, bridge.second, bridge.status, bridge.add_peer,
                                    bridge.uninstall_dry, bridge.uninstall))
    for secret in bridge.secrets:
        assert len(secret) == 64
        assert not leaks(secret, text), "a token leaked"
    assert f"token ****{bridge.laptop_token[-4:]} written" in bridge.first.out  # shown masked, not hidden


def test_bridge_status(bridge):
    status = bridge.status
    assert status.res.returncode == 0, status.text
    assert "service: running" in status.out
    assert f"firewall: rule present for {SUBNET} on port {bridge.port}" in status.out
    assert "bridge: ok" in status.out
    assert status.changed_nothing()


def test_bridge_new_peer_on_rerun_restarts_service(bridge):
    add = bridge.add_peer
    assert add.res.returncode == 0, add.text
    assert bridge.peers_after_add == {"hub", "laptop", "desk"}
    restart = ["systemctl", "restart", "ai-connect"] if bridge.target == "linux" else ["schtasks", "/Run"]
    assert any(c[:len(restart)] == restart for c in add.calls), add.calls
    assert "already done: peer 'laptop'" in add.out


def test_uninstall_dry_run_changes_nothing(bridge):
    dry = bridge.uninstall_dry
    assert dry.res.returncode == 0, dry.text
    assert dry.out.count("would:") >= 3
    assert dry.changed_nothing(), dry.mutations


def test_uninstall_removes_everything_and_reruns_clean(bridge):
    assert bridge.uninstall.res.returncode == 0, bridge.uninstall.text
    state = bridge.state_after_uninstall
    assert not bridge.config_after_uninstall and not bridge.unit_after_uninstall
    if bridge.target == "linux":
        assert state["ufw"] == [] and not state["units"]["ai-connect"]["active"]
    else:
        assert state["tasks"] == {} and state["rules"] == {}
    again = bridge.uninstall_again
    assert again.res.returncode == 0, again.text
    assert again.changed_nothing(), again.mutations
    assert len(already(again.res)) == 5, again.out


def test_bridge_without_tailscale_ip_fails(box):
    box.set(ts_ip="")
    res = box.deploy("bridge", "--name", "hub")
    assert res.returncode == 1
    assert "no Tailscale IPv4 address" in res.stderr
    assert not box.config_file.exists() and box.mutations() == []


def test_bridge_without_tailscale_installed(box):
    box.remove_tool("tailscale")
    if shutil.which("tailscale", path=box.env["PATH"]):
        pytest.skip("a real tailscale is on the minimal PATH")
    res = box.deploy("bridge", "--name", "hub")
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


def peer_args(port: int, token_file: Path) -> list[str]:
    return ["peer", "--name", "laptop", "--bridge", "127.0.0.1", "--port", str(port), "--token-file", str(token_file)]


@pytest.fixture(scope="module")
def peer(tmp_path_factory, venv):
    """A peer machine, off the tailnet at first: dry run -> deploy -> the same again -> status."""
    tmp = tmp_path_factory.mktemp("peer")
    box = Box(tmp, venv, NATIVE)
    box.set(ts_backend="Stopped", ts_ip="")
    token_file = tmp / "laptop.token"
    token_file.write_text(PEER_TOKEN + "\n", encoding="utf-8")
    server = FakeBridge(lambda: {hashlib.sha256(PEER_TOKEN.encode()).hexdigest()})
    args, key = peer_args(server.port, token_file), {"TS_AUTHKEY": AUTH_KEY}
    run = SimpleNamespace()
    run.box, run.port = box, server.port
    try:
        run.dry = Phase(box, *args, "--dry-run", extra_env=key)
        run.first = Phase(box, *args, extra_env=key)
        run.state = box.state()
        run.client = box.config()["client"]
        run.second = Phase(box, *args, extra_env=key)
        run.status = Phase(box, "status")
    finally:
        server.close()
    return run


def test_peer_happy_path(peer):
    first = peer.first
    assert first.res.returncode == 0, first.text
    assert [s.split("]")[0] for s in steps(first.out)] == [f"[{n}/5" for n in range(1, 6)]
    assert peer.state["plugins"] == ["ai-connect@useful-claude-add-ons"]
    assert str(PLUGIN / "client" / "server.py") in peer.state["mcp"]["ai-connect"]
    assert peer.state["ts_backend"] == "Running"
    up = [c for c in first.calls if c[:2] == ["tailscale", "up"]]
    assert len(up) == 1 and "--hostname=laptop" in up[0]
    assert (peer.client["name"], peer.client["token"], peer.client["bridge_url"]) == \
        ("laptop", PEER_TOKEN, f"ws://127.0.0.1:{peer.port}")
    assert "accepted this machine's token" in first.out


def test_peer_rerun_is_idempotent(peer):
    second = peer.second
    assert second.res.returncode == 0, second.text
    assert second.changed_nothing(), second.mutations
    assert len(already(second.res)) == 5, second.out  # deps, plugin, MCP server, VPN, config


def test_peer_dry_run_changes_nothing(peer):
    dry = peer.dry
    assert dry.res.returncode == 0, dry.text
    assert dry.out.count("would:") >= 5, dry.out
    assert dry.changed_nothing(), dry.mutations


def test_peer_never_prints_token_or_auth_key(peer):
    text = "".join(p.text for p in (peer.dry, peer.first, peer.second, peer.status))
    for secret in (PEER_TOKEN, AUTH_KEY):
        assert not leaks(secret, text), "a secret leaked"
    assert "token ****beef" in peer.dry.out and "token ****beef" in peer.first.out
    key_on_argv = [c for c in peer.first.calls if any(AUTH_KEY in a for a in c) and c[:2] != ["tailscale", "up"]]
    assert key_on_argv == []  # only `tailscale up --auth-key=` itself ever carries it


def test_peer_wrong_token_fails_verification(box, tmp_path):
    box.set(ts_backend="Running")
    wrong = tmp_path / "wrong.token"
    wrong.write_text("0123456789abcdef" * 4, encoding="utf-8")
    server = FakeBridge(lambda: {hashlib.sha256(PEER_TOKEN.encode()).hexdigest()})
    try:
        res = box.deploy(*peer_args(server.port, wrong))
    finally:
        server.close()
    assert res.returncode == 1
    assert "refused this machine's token" in res.stderr
    assert not leaks("0123456789abcdef" * 4, output(res))


def test_peer_without_auth_key_when_off_tailnet_fails(box, tmp_path):
    box.set(ts_backend="Stopped", ts_ip="")
    token_file = tmp_path / "laptop.token"
    token_file.write_text(PEER_TOKEN, encoding="utf-8")
    res = box.deploy(*peer_args(9, token_file))
    assert res.returncode == 1
    assert "no auth key" in res.stderr
    assert not box.config_file.exists() and box.mutations() == []


# ---------------------------------------------------------------- bad arguments


@pytest.fixture(scope="module")
def args_box(tmp_path_factory, venv):
    return Box(tmp_path_factory.mktemp("bad-args"), venv, NATIVE)


@pytest.mark.parametrize("args", [
    [], ["bogus"], ["peer", "--bridge", "127.0.0.1"], ["peer", "--name", "laptop"],
    ["peer", "--name", "bad name!", "--bridge", "127.0.0.1"], ["peer", "--name", "laptop", "--bridge", "a b"],
    ["peer", "--name", "laptop", "--bridge", "127.0.0.1"], ["bridge", "--port", "70000"],
    ["bridge", "--vpn-subnet", "nope"], ["bridge", "--peer", "-x-"], ["uninstall"], ["status", "--dry-run"],
], ids=lambda a: " ".join(a) or "no-args")
def test_bad_arguments_exit_2_and_change_nothing(args_box, args):
    phase = Phase(args_box, *args)
    assert phase.res.returncode == 2, phase.text
    assert phase.res.stderr.strip()
    assert phase.calls == [] and phase.changed_nothing()


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
def test_sh_and_ps1_print_the_same_steps(box, tmp_path):
    cases = [["bridge", "--name", "hub", "--peer", "laptop", "--dry-run"], ["uninstall", "--dry-run"],
             ["peer", "--name", "bad name!", "--bridge", "x"]]
    for args in cases:
        sh, ps1 = _sh(box, args), _ps1(box, args, tmp_path)
        assert (sh.returncode, sh.stdout, sh.stderr) == (ps1.returncode, ps1.stdout, ps1.stderr), args
        assert sh.stdout or sh.stderr
    assert len(steps(_sh(box, cases[0]).stdout)) == 6
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
