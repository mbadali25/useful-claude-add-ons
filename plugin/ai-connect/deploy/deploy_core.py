"""What every deploy subcommand shares: output that never shows a secret, the step
counter with its dry run, how a tool is run, and where the venv and Tailscale are.

deploy.py and the modules it registers (ts_install.py, tailnet_setup.py,
smoke_test.py) import from here, so none of them imports another's internals.
"""
from __future__ import annotations

import ipaddress
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent
sys.path.insert(0, str(PLUGIN / "vpn"))
import tsadmin  # noqa: E402  pylint: disable=wrong-import-position,import-error

EXIT_OK, EXIT_FAILED, EXIT_USAGE = 0, 1, 2
DEFAULT_PORT = 9999
CONFIG_DIR = Path.home() / ".config" / "ai-connect"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
# What keeps running after deploy (the Bridge service, the MCP server) runs from a copy of this plugin and
# a venv beside it, both outside the checkout deploy runs from: a worktree or a clone can then be deleted,
# and a checkout's own venv is never picked up. AI_CONNECT_HOME moves both
APP_HOME = Path(os.environ.get("AI_CONNECT_HOME") or Path.home().joinpath(
    *(("AppData", "Local") if os.name == "nt" else (".local", "share")), "ai-connect"))
APP = APP_HOME / "app"
VENV = Path(os.environ.get("AI_CONNECT_VENV") or APP_HOME / "venv")
# Root needs no sudo, and a machine that runs as root may not have it. The variable is a test seam
IS_ROOT = os.environ.get("AI_CONNECT_DEPLOY_ROOT") == "1" or getattr(os, "geteuid", lambda: 1000)() == 0


class Failure(Exception):
    """A refusal with a one-line reason and an exit code."""

    def __init__(self, message: str, code: int = EXIT_FAILED):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------- output


# Where the text for a person goes: stderr once a command prints JSON on stdout (human_to_stderr);
# None is whatever sys.stdout is when the line is printed
_STREAM: list = [None]


def human_to_stderr() -> None:
    _STREAM[0] = sys.stderr


def out(msg: str = "") -> None:
    print(tsadmin.redact(msg), file=_STREAM[0] or sys.stdout, flush=True)


def mask(secret: str) -> str:
    """Never the secret: a fixed mask, plus its last 4 characters when it is long enough to spare them."""
    return "****" + secret[-4:] if len(secret) >= 24 else "****"


def has_terminal() -> bool:
    """True when a person can be asked: stdin is a real terminal. On Windows NUL also claims
    to be a tty, and a prompt on it would wait forever, so the console itself is asked."""
    try:
        if sys.stdin is None or not sys.stdin.isatty():
            return False
        if os.name != "nt":
            return True
        import ctypes  # pylint: disable=import-outside-toplevel
        import msvcrt  # pylint: disable=import-outside-toplevel,import-error
        handle = msvcrt.get_osfhandle(sys.stdin.fileno())
        return bool(ctypes.windll.kernel32.GetConsoleMode(handle, ctypes.byref(ctypes.c_ulong())))
    except (OSError, ValueError, AttributeError):
        return False


class Run:
    """One deploy invocation: dry-run flag, step counter, what changed."""

    def __init__(self, dry_run: bool, total: int):
        self.dry_run = dry_run
        self.total = total
        self.number = 0
        self.config_changed = False
        # The same run for a machine: [{"step": title, "results": [{"status", "detail"}]}], secrets redacted
        self.log: list[dict] = []

    def step(self, title: str) -> None:
        self.number += 1
        self.log.append({"step": title, "results": []})
        out(f"[{self.number}/{self.total}] {title}")

    def record(self, status: str, msg: str) -> None:
        if self.log:
            self.log[-1]["results"].append({"status": status, "detail": tsadmin.redact(msg)})

    def already(self, msg: str) -> None:
        self.record("already", msg)
        out(f"  already done: {msg}")

    def change(self, msg: str, action) -> None:
        """Do one change, or in a dry run only say it would."""
        if self.dry_run:
            self.record("would", msg)
            out(f"  would: {msg}")
            return
        action()
        self.record("done", msg)
        out(f"  done: {msg}")


# ---------------------------------------------------------------- processes


def tool(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise Failure(f"{name} not found on PATH")
    return found


def no_tools() -> None:
    """A dry run: from here on this process runs no tool, no sudo and no CLI. Only this program's own
    helper may still run, in its own venv, to read config.yaml (deps_ok, config_tool inspect)."""
    tsadmin.NO_EXEC[0] = True


def _refuse_in_dry_run(argv: list[str]) -> None:
    own = venv_python()
    if tsadmin.NO_EXEC[0] and not (own and Path(argv[0]) == own):
        raise Failure(f"internal: a dry run runs no tool, and {Path(argv[0]).name} was about to run")


def run(argv: list[str], *, stdin_text: str | None = None, env: dict | None = None,
        timeout: float = 300) -> subprocess.CompletedProcess:
    _refuse_in_dry_run(argv)
    try:
        # A tool that writes its code page (cp1252, cp850 on a localised Windows) must not kill the reader
        # thread: that leaves stdout None and the caller fails on it
        return subprocess.run(argv, input=stdin_text, stdin=None if stdin_text is not None else subprocess.DEVNULL,
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=timeout, check=False, env=env)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(argv, 124, "", f"{Path(argv[0]).name} timed out")


def interactive(argv: list[str], *, timeout: float = 1800) -> int:
    """Run a tool that may ask the person something (sudo's password, UAC, a browser login):
    it keeps this terminal, and nothing it prints passes through this process."""
    _refuse_in_dry_run(argv)
    sys.stdout.flush()
    try:
        # Once stdout is kept for JSON, the tool's own output goes where the text for a person goes
        stdout = sys.stderr if _STREAM[0] is sys.stderr else None
        return subprocess.run(argv, check=False, timeout=timeout, stdout=stdout).returncode
    except subprocess.TimeoutExpired:
        return 124


def must(res: subprocess.CompletedProcess, what: str) -> subprocess.CompletedProcess:
    if res.returncode != 0:
        detail = (res.stderr or res.stdout).strip().splitlines()
        raise Failure(f"{what} failed (exit {res.returncode}): {detail[-1] if detail else 'no output'}")
    return res


def privileged(name: str) -> list[str]:
    """argv prefix for a root-only Linux tool: sudo unless already root."""
    if IS_ROOT:
        return [tool(name)]
    return [tool("sudo"), tool(name)]


# ---------------------------------------------------------------- venv


def venv_python() -> Path | None:
    for parts in (("Scripts", "python.exe"), ("bin", "python")):
        cand = VENV.joinpath(*parts)
        if cand.is_file():
            return cand
    return None


def config_tool(*args: str, env_extra: dict | None = None, timeout: float = 300) -> dict:
    """Run config_tool.py with the venv's Python (it imports installer.py, which needs PyYAML)."""
    python = venv_python()
    if python is None:
        raise Failure(f"no venv at {VENV}; run `deploy bridge` or `deploy peer` first")
    env = dict(os.environ, **(env_extra or {}))
    res = run([str(python), str(HERE / "config_tool.py"), *args], env=env, timeout=timeout)
    try:
        payload = json.loads(res.stdout.strip().splitlines()[-1]) if res.stdout.strip() else {}
    except ValueError:
        payload = {}
    if res.returncode != 0:
        # Only the helper's own one-line reason: its raw output could quote config.yaml, which holds tokens
        raise Failure(str(payload.get("error") or f"config_tool {args[0]} failed (exit {res.returncode})"))
    return payload


# ---------------------------------------------------------------- tailscale


def backend_state() -> str | None:
    """'Running', 'NeedsLogin', ... or None when tailscaled could not be asked."""
    return tsadmin.backend_state(tsadmin.tailscale_bin(), userspace=tsadmin.userspace_socket().exists())


def ts_prefs() -> dict | None:
    """Tailscale's settings on this machine (RouteAll, ExitNodeID, CorpDNS, ...), or None when unreadable."""
    res = tsadmin.run_ts(tsadmin.tailscale_bin(), ["debug", "prefs"],
                         userspace=tsadmin.userspace_socket().exists(), timeout=30)
    try:
        prefs = json.loads(res.stdout) if res.returncode == 0 else None
    except ValueError:
        return None
    return prefs if isinstance(prefs, dict) else None


def tailscale_ip() -> str:
    res = run([tsadmin.tailscale_bin(), "ip", "-4"], timeout=30)
    first = res.stdout.strip().splitlines()[0].strip() if res.stdout.strip() else ""
    try:
        ipaddress.IPv4Address(first)
    except ValueError:
        raise Failure("this machine has no Tailscale IPv4 address (`tailscale ip -4`); "
                      "join the tailnet first (tailscale up)") from None
    return first
