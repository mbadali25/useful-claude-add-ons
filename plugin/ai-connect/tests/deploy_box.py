"""A fake machine for the deploy suites: HOME, a PATH of fakes, and how to run deploy on it.

Every system tool deploy drives (tailscale, sudo, systemctl, ufw, firewall-cmd, schtasks,
powershell, netsh, claude, and the installers curl, sh, winget, msiexec, brew) is tests/fake_deploy_bin.py
on a minimal PATH, HOME is a tmp dir, systemd units go to a tmp dir, the credential
store is tests/fake_keyring, and the "venv" is a pip-less venv that sees this
interpreter's packages. A small WebSocket server stands in for the Bridge and checks
the Bearer token the way the real one does.
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
# The installers are always fakes too: no test may reach a real curl, winget or brew
TOOLS = ("tailscale", "sudo", "tee", "rm", "systemctl", "ufw", "schtasks", "netsh", "claude",
         "firewall-cmd", "powershell", "ip", "curl", "sh", "install", "apt-get", "winget", "msiexec", "brew")
SUBNET = "100.64.0.0/10"
AUTH_KEY = "tskey-auth-kDEPLOY123-AuthKeyMaterialThatMustNotLeak0123"
PEER_TOKEN = "f00dfacecafe" * 5 + "beef"
# Calls that change something; a rerun or a dry run must make none of them
MUTATING = {("tee",), ("rm",), ("systemctl", "enable"), ("systemctl", "restart"), ("systemctl", "disable"),
            ("systemctl", "daemon-reload"), ("ufw", "allow"), ("ufw", "delete"), ("schtasks", "/Create"),
            ("firewall-cmd", "--reload"), ("firewall-cmd", "--permanent", "--add-rich-rule"),
            ("firewall-cmd", "--permanent", "--remove-rich-rule"), ("tailscale", "set"),
            ("schtasks", "/Run"), ("schtasks", "/End"), ("schtasks", "/Delete"),
            ("netsh", "advfirewall", "firewall", "add"), ("netsh", "advfirewall", "firewall", "delete"),
            ("claude", "plugin", "install"),
            ("claude", "plugin", "uninstall"), ("claude", "mcp", "add"), ("claude", "mcp", "remove"),
            ("tailscale", "up"), ("curl",), ("sh",), ("winget",), ("msiexec",), ("brew",),
            ("install",), ("apt-get",)}

PWSH_CANDIDATES = [r"C:\Program Files\PowerShell\7\pwsh.exe", "/usr/bin/pwsh", "/usr/local/bin/pwsh",
                   "/opt/homebrew/bin/pwsh"]
PWSH = next((p for p in PWSH_CANDIDATES if os.path.isfile(p)), None)
GIT_BASH = r"C:\Program Files\Git\bin\bash.exe"
BASH = (GIT_BASH if os.path.isfile(GIT_BASH) else None) if os.name == "nt" else shutil.which("bash")
FAKE_KEYRING = Path(__file__).resolve().parent / "fake_keyring"
# sitecustomize there guards every Python the Box starts: no socket leaves this machine (conftest.py)
NETGUARD = Path(__file__).resolve().parent / "netguard"


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
        # The directory deploy is run in: --scope project registers the MCP server and writes the
        # peer-state hooks for "this project", which must never be the checkout the suite runs from
        self.project = tmp_path / "project"
        self.project.mkdir()
        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        self.state_file = tmp_path / "fake-state.json"
        self.log = tmp_path / "fake-log.jsonl"
        self.log.write_text("", encoding="utf-8")
        self.set(ts_ip="127.0.0.1", ts_backend="Running", shim=self.shim("{name}"))
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
                        AI_CONNECT_DEPLOY_HEALTH_WAIT="3", AI_CONNECT_DEPLOY_STOP_WAIT="1",
                        AI_CONNECT_TSD_WAIT="0",
                        XDG_CACHE_HOME=str(tmp_path / "xdg-cache"), PYTHONIOENCODING="utf-8",
                        # No real Tailscale install dir, credential store or OAuth file is ever looked at
                        FAKE_DEPLOY_BIN=str(self.bin), AI_CONNECT_TAILSCALE_DIRS=str(tmp_path / "no-tailscale"),
                        AI_CONNECT_OS_RELEASE=str(tmp_path / "os-release"),
                        PYTHONPATH=os.pathsep.join([str(FAKE_KEYRING), str(NETGUARD)]),
                        FAKE_KEYRING_FILE=str(tmp_path / "keyring.json"),
                        AI_CONNECT_OAUTH_FILE=str(self.home / ".config" / "ai-connect" / "tailscale-oauth.json"))
        for name in ("TS_API_TOKEN", "TS_OAUTH_CLIENT_ID", "TS_OAUTH_CLIENT_SECRET",
                     "AI_CONNECT_DEPLOY_PLATFORM", "AI_CONNECT_DEPLOY_ROOT", "AI_CONNECT_HOME",
                     # Claude Code's settings are then the fake HOME's, never the real ones of whoever runs this
                     "CLAUDE_CONFIG_DIR"):
            self.env.pop(name, None)
        # Never the real Tailscale API: a closed loopback port unless a test passes its fake's address
        self.env["TS_API_BASE"] = "http://127.0.0.1:9/api/v2"
        self.target = target
        # Where deploy installs the copy of the plugin the service and the MCP server run from
        self.app = self.home.joinpath(*(("AppData", "Local") if os.name == "nt" else (".local", "share")),
                                      "ai-connect", "app")

    @staticmethod
    def shim(name: str) -> str:
        """The launcher that makes fake_deploy_bin.py answer as the tool called name."""
        if os.name == "nt":
            return f'@"{sys.executable}" "{FAKE}" {name} %*\r\n'
        return f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" {name} "$@"\n'

    def add_tool(self, name: str) -> None:
        path = self.bin / (f"{name}.cmd" if os.name == "nt" else name)
        path.write_bytes(self.shim(name).encode("utf-8"))
        path.chmod(0o755)

    def remove_tool(self, name: str) -> None:
        """Take a fake off the PATH. Never lets its real counterpart answer instead: the test is skipped."""
        for path in (self.bin / name, self.bin / f"{name}.cmd"):
            path.unlink(missing_ok=True)
        if shutil.which(name, path=self.env["PATH"]):
            pytest.skip(f"a real {name} is on the minimal PATH; this test would reach it")

    def set(self, **values) -> None:
        state = self.state() if self.state_file.exists() else {}
        state.update(values)
        self.state_file.write_text(json.dumps(state), encoding="utf-8")

    def state(self) -> dict:
        return json.loads(self.state_file.read_text(encoding="utf-8"))

    def calls(self) -> list[list[str]]:
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines() if line]

    def mutations(self) -> list[list[str]]:
        # "--add-rich-rule=<rule>" is one word: compared without what follows its "="
        return [c for c in self.calls()
                if any(tuple(w.split("=", 1)[0] for w in c[:len(m)]) == m for m in MUTATING)]

    def clear_log(self) -> None:
        self.log.write_text("", encoding="utf-8")

    @property
    def user_settings(self) -> Path:
        """Claude Code's user settings on the fake machine."""
        return self.home / ".claude" / "settings.json"

    @property
    def project_settings(self) -> Path:
        """The settings of the project deploy is run in that are this machine's alone."""
        return self.project / ".claude" / "settings.local.json"

    @property
    def config_file(self) -> Path:
        return self.home / ".config" / "ai-connect" / "config.yaml"

    def config(self) -> dict:
        return yaml.safe_load(self.config_file.read_text(encoding="utf-8"))

    def deploy(self, *args: str, extra_env: dict | None = None) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(DEPLOY), *args], capture_output=True, text=True, check=False,
                              stdin=subprocess.DEVNULL, env=dict(self.env, **(extra_env or {})), timeout=180,
                              cwd=self.project)

    def snapshot(self) -> dict:
        """Every file under the fake machine's HOME, systemd dir and project, with its bytes."""
        return {str(p): p.read_bytes() for root in (self.home, self.systemd, self.project)
                for p in sorted(root.rglob("*"))
                if p.is_file()}


NATIVE = "windows" if os.name == "nt" else "linux"


def output(res: subprocess.CompletedProcess) -> str:
    return res.stdout + res.stderr


def steps(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("[")]


def leaks(secret: str, text: str) -> bool:
    """True when any 12-character run of the secret shows up in text."""
    return any(secret[i:i + 12] in text for i in range(len(secret) - 11))


def owner_only(path: Path) -> bool:
    """True when only its owner may reach path: no group or other bit, on Windows an ACL of this user alone."""
    if os.name != "nt":
        return path.stat().st_mode & 0o077 == 0
    acl = subprocess.run(["icacls", str(path)], capture_output=True, text=True, check=True,
                         stdin=subprocess.DEVNULL).stdout
    entries = [line.replace(str(path), "").strip() for line in acl.splitlines() if ":(" in line]
    user = os.environ["USERNAME"].lower()
    return bool(entries) and all(entry.lower().split(":(")[0].rsplit("\\", 1)[-1] == user and "(I)" not in entry
                                 for entry in entries)


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


class OwnBridge:
    """A fake Bridge that accepts the peers in the box's own config, for a test that deploys one."""

    def __init__(self, box: Box):
        def accepted():
            return set(box.config()["auth"]["peers"].values()) if box.config_file.exists() else set()
        self.server = FakeBridge(accepted)
        self.args = ["bridge", "--name", "hub", "--port", str(self.server.port)]

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.server.close()
