#!/usr/bin/env python3
"""AI-Connect deploy: one core behind the deploy.sh / deploy.ps1 pair.

  deploy bridge [--name N] [--peer P ...] [--port N] [--vpn-subnet CIDR] [--dry-run]
  deploy peer --name N --bridge HOST [--port N] [--auth-key-file F] [--token-file F] [--dry-run]
              [--register-mcp [--scope project|user]] [--install-hooks]      both off by default
  deploy peer --name N --bridge HOST --print-enrolment      make this peer's own token, print only its hash
  deploy add-peer --name N --token-sha256 HEX [--dry-run]   on the Bridge: let that peer in by the hash
  deploy invite --name N [--bridge HOST] [--expiry 1h] [--ephemeral] [--out F] [--dry-run]
                                                            on the Bridge: a one-use join key as an invite code
  deploy join (--invite-file F | --invite | --name N --bridge HOST) [--with-hooks] [--register-mcp] [--dry-run]
                                                            a new machine: Tailscale, the tailnet, its token, config
  deploy approve --name N [--token-sha256 HEX] [--dry-run]  add-peer, the restart, and the node's key expiry off
  deploy remove --name N --yes [--dry-run]                  the node off the tailnet and out of the Bridge
  deploy list                                               tailnet nodes beside the Bridge's peers
  deploy status
  deploy uninstall --yes [--purge] [--dry-run]
  deploy tailnet-setup [--apply] [--admin WHO] [--acl FILE] [--device NAME]     (tailnet_setup.py)
  deploy test --bridge HOST --name N [--port N] [--token-file F]                (smoke_test.py)

Secrets never travel on the command line and are never printed: the peer
token comes from --token-file or AI_CONNECT_PEER_TOKEN, the one-off Tailscale
auth key from --auth-key-file or TS_AUTHKEY. Every step checks what is already
there first and says "already done" instead of doing it again. --dry-run runs
no tool at all and needs no token or key file: it prints what it may change, and changes nothing.
bridge and peer install Tailscale when it is missing (ts_install.py).

Exit codes: 0 done, 1 a step failed, 2 bad arguments, 3 tailscale not installed.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import getpass
import hashlib
import ipaddress
import json
import os
import re
import secrets
import shutil
import socket
import sys
import tempfile
import time
from pathlib import Path

import smoke_test  # pylint: disable=import-error
import tailnet_setup  # pylint: disable=import-error
import ts_install  # pylint: disable=import-error
from deploy_core import (APP, APP_HOME, CONFIG_DIR, CONFIG_FILE, DEFAULT_PORT, EXIT_FAILED,  # pylint: disable=import-error
                         EXIT_OK, EXIT_USAGE, IS_ROOT, PLUGIN, VENV, Failure, Run, backend_state, config_tool,
                         has_terminal, interactive, mask, must, no_tools, out, privileged, run, tailscale_ip, tool,
                         ts_prefs, ts_self, tsadmin, venv_python)

# Same names install.sh / install.ps1 use, so their --status and --uninstall see these
UNIT = "ai-connect"
TASK = "AI-Connect Bridge"
RULE = "AI-Connect Bridge"
PLUGIN_ID = "ai-connect@useful-claude-add-ons"
MCP_SERVER = "ai-connect"
DEFAULT_SUBNET = "100.64.0.0/10"
TOKEN_DIR = CONFIG_DIR / "peer-tokens"
# A peer's own token when it made it itself (--print-enrolment): only its hash ever leaves this machine
OWN_TOKEN = CONFIG_DIR / "own-peer.token"
# Written when config.yaml changes and removed once the Bridge has restarted: a run that failed in
# between leaves it, and the next run restarts a Bridge that is still serving the old config
RESTART_PENDING = CONFIG_DIR / ".bridge-restart-pending"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
HOSTNAME_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,252})$")
# Test seams: which OS's service/firewall tools to drive, and where systemd units live
TARGET = os.environ.get("AI_CONNECT_DEPLOY_OS") or ("windows" if os.name == "nt" else "linux")
SYSTEMD_DIR = Path(os.environ.get("AI_CONNECT_SYSTEMD_DIR") or "/etc/systemd/system")
HEALTH_WAIT = float(os.environ.get("AI_CONNECT_DEPLOY_HEALTH_WAIT") or 20)
STOP_WAIT = float(os.environ.get("AI_CONNECT_DEPLOY_STOP_WAIT") or 15)


# ---------------------------------------------------------------- venv + config tool


# Written into the venv after its pip install: a newer checkout with other pins is installed again
REQUIREMENTS_DIGEST = VENV / ".ai-connect-requirements.sha256"


def requirements_digest() -> str:
    return hashlib.sha256((PLUGIN / "requirements.txt").read_bytes()).hexdigest()


def deps_ok(python: Path) -> bool:
    """The venv has this checkout's requirements: the same pins installed, and the modules there."""
    try:
        if REQUIREMENTS_DIGEST.read_text(encoding="utf-8").strip() != requirements_digest():
            return False
    except OSError:
        return False
    # find_spec, not import: importing fastmcp takes seconds, and this runs on every invocation
    probe = ("import importlib.util as u, sys; "
             "sys.exit(any(u.find_spec(m) is None for m in ('yaml', 'websockets', 'aiosqlite', 'fastmcp')))")
    return run([str(python), "-c", probe], timeout=120).returncode == 0


def inspect_config() -> dict | None:
    """The config's non-secret facts, or None when no venv can read it yet."""
    if venv_python() is None:
        return None
    return config_tool("inspect")


# Not installed: venvs, tests, caches, and what a checkout may hold that is not the plugin's (logs, databases)
APP_SKIP_DIRS = {"venv", ".venv", "ENV", "tests", "__pycache__", ".pytest_cache", ".ruff_cache", ".git", ".idea",
                 ".vscode"}
APP_SKIP_SUFFIXES = {".pyc", ".pyo", ".db", ".log", ".token"}


def app_files(root: Path) -> dict[str, Path]:
    """The plugin's files deploy installs, by their path relative to root."""
    files = {}
    for here, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in APP_SKIP_DIRS]
        for name in names:
            path = Path(here) / name
            if path.suffix not in APP_SKIP_SUFFIXES and name != "config.yaml":
                files[path.relative_to(root).as_posix()] = path
    return files


def step_app(r: Run, restart_on_change: bool) -> None:
    """Bring the copy at APP up to this checkout's files; the service and the MCP server run from it."""
    if PLUGIN.resolve() == APP.resolve():
        r.already(f"deploy runs from {APP} itself")
        return
    want = app_files(PLUGIN)
    have = app_files(APP) if APP.is_dir() else {}
    changed = sorted(rel for rel, path in want.items()
                     if rel not in have or have[rel].read_bytes() != path.read_bytes())
    stale = sorted(set(have) - set(want))
    if not changed and not stale:
        r.already(f"{APP} matches this checkout")
        return

    def sync() -> None:
        for rel in changed:
            dest = APP / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            # Replaced, not rewritten in place: the running Bridge may have the old file open
            part = dest.with_name(dest.name + ".deploy-part")
            shutil.copy2(want[rel], part)
            os.replace(part, dest)
        for rel in stale:
            (APP / rel).unlink(missing_ok=True)
    what = f"{len(changed)} changed, {len(stale)} removed" if have else f"{len(changed)} files"
    if have and (restart_on_change or bridge_here()):
        # A running Bridge still has the old code loaded. Owed before the copy, so a copy that stops
        # halfway, or one made for the MCP server, still restarts it on the next deploy bridge
        owe_restart(r)
    r.change(f"install this checkout's files to {APP} ({what})", sync)


def bridge_here() -> bool:
    """This machine runs the Bridge: its config listens, and its own peer is one of auth.peers."""
    facts = inspect_config() or {}
    return bool(facts.get("host")) and facts.get("name") in (facts.get("peers") or [])


def step_deps(r: Run) -> None:
    r.step("Python venv and dependencies")
    python = venv_python()
    if python and deps_ok(python):
        r.already(f"venv {VENV} has the dependencies")
        return
    if python is None:
        r.change(f"create venv {VENV}", lambda: must(run([sys.executable, "-m", "venv", str(VENV)]), "python -m venv"))
    requirements = PLUGIN / "requirements.txt"  # the same file the copy at APP has

    def install() -> None:
        must(run([str(venv_python()), "-m", "pip", "install", "-q", "-r", str(requirements)], timeout=900),
             "pip install")
        REQUIREMENTS_DIGEST.write_text(requirements_digest() + "\n", encoding="utf-8")

    r.change(f"install {requirements.name} into the venv", install)


# ---------------------------------------------------------------- service


def unit_text(python: str) -> str:
    # The unit install.sh writes, so either installer can update the other's
    return (f"[Unit]\nDescription=AI-Connect Bridge Server\nAfter=network.target \n\n"
            f"[Service]\nType=simple\nUser={getpass.getuser()}\nWorkingDirectory={APP}\n"
            f"ExecStart={python} -m server.main\nRestart=always\nRestartSec=5\n"
            f"Environment=PYTHONUNBUFFERED=1\n\n[Install]\nWantedBy=multi-user.target\n")


def task_xml(pythonw: str) -> str:
    # install.ps1's task: at logon, as the user without elevation, restarted on failure, no time limit
    user = f"{os.environ.get('USERDOMAIN', socket.gethostname())}\\{getpass.getuser()}"
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers><LogonTrigger><Enabled>true</Enabled><UserId>{user}</UserId></LogonTrigger></Triggers>
  <Principals><Principal id="Author"><UserId>{user}</UserId><LogonType>InteractiveToken</LogonType>
    <RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <RestartOnFailure><Interval>PT1M</Interval><Count>999</Count></RestartOnFailure>
  </Settings>
  <Actions Context="Author"><Exec><Command>{pythonw}</Command><Arguments>-m server.main</Arguments>
    <WorkingDirectory>{APP}</WorkingDirectory></Exec></Actions>
</Task>
"""


# The state as a number (4 is Running): schtasks prints it as a word in the display language,
# "Wird ausgeführt" on a German Windows. A query that fails ends PowerShell with an error, not with "absent".
# Then the program and the working directory the task runs, one line each.
TASK_STATE = ("$ErrorActionPreference = 'Stop'; "
              f"$t = Get-ScheduledTask | Where-Object {{ $_.TaskName -eq '{TASK}' }} | Select-Object -First 1; "
              "if ($null -eq $t) { 'absent' } else { [int]$t.State; $t.Actions[0].Execute; "
              "$t.Actions[0].WorkingDirectory }")


def task_info() -> tuple[str, str, str]:
    """The scheduled task's state ('running', 'stopped' or 'absent'), program and working directory."""
    res = run([tool("powershell"), "-NoProfile", "-NonInteractive", "-Command", TASK_STATE], timeout=60)
    lines = [line.strip() for line in res.stdout.strip().splitlines()] or [""]
    word = lines[0]
    if res.returncode != 0 or not (word == "absent" or word.isdigit()):
        raise Failure(f"could not read the state of scheduled task '{TASK}' (powershell exit {res.returncode})")
    state = "absent" if word == "absent" else "running" if word == "4" else "stopped"
    return state, *(lines[1:3] + ["", ""])[:2]


def service_state() -> str:
    """'running', 'stopped' or 'absent'. Raises when the state cannot be read: unknown is none of the three."""
    if TARGET == "linux":
        if not (SYSTEMD_DIR / f"{UNIT}.service").is_file():
            return "absent"
        res = run([tool("systemctl"), "is-active", UNIT], timeout=30)
        return "running" if res.stdout.strip() == "active" else "stopped"
    return task_info()[0]


def owe_restart(r: Run) -> None:
    """config.yaml changed (or is about to): the running Bridge has to be restarted to read it."""
    r.config_changed = True
    if not r.dry_run:
        RESTART_PENDING.parent.mkdir(parents=True, exist_ok=True)
        RESTART_PENDING.write_text("config.yaml changed; the Bridge has not been restarted since\n", encoding="utf-8")


def stop_task() -> None:
    """End the scheduled task and see it stopped. /End succeeds on a task that is not running, and
    /Run starts nothing while an instance still runs (MultipleInstancesPolicy IgnoreNew)."""
    must(run([tool("schtasks"), "/End", "/TN", TASK]), "schtasks /End")
    deadline = time.monotonic() + STOP_WAIT
    while service_state() == "running":
        if time.monotonic() >= deadline:
            raise Failure(f"scheduled task '{TASK}' is still running after schtasks /End")
        time.sleep(0.5)


def step_service(r: Run) -> None:
    r.step("Bridge service")
    step_app(r, restart_on_change=True)
    what = f"{UNIT}.service" if TARGET == "linux" else f"scheduled task '{TASK}'"
    if r.dry_run:  # asks no tool what is running
        r.change(f"install or update {what} and (re)start it, unless it already runs with this config", lambda: None)
        return
    if RESTART_PENDING.exists():
        r.config_changed = True
    python = venv_python() or (VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
    if TARGET == "linux":
        state = service_state()
        unit = SYSTEMD_DIR / f"{UNIT}.service"
        want = unit_text(str(python))
        current = unit.read_text(encoding="utf-8") if unit.is_file() else None
        enabled = (state != "absent"
                   and run([tool("systemctl"), "is-enabled", UNIT], timeout=30).stdout.strip() == "enabled")
        if current == want and enabled and state == "running" and not r.config_changed:
            r.already(f"{UNIT}.service installed, enabled and running")
            return
        if current != want:
            r.change(f"write {unit}", lambda: must(run(privileged("tee") + [str(unit)], stdin_text=want), "write unit"))
            r.change("systemctl daemon-reload",
                     lambda: must(run(privileged("systemctl") + ["daemon-reload"]), "daemon-reload"))
        if not enabled:
            r.change(f"enable {UNIT}.service",
                     lambda: must(run(privileged("systemctl") + ["enable", UNIT]), "systemctl enable"))
        def restart_unit() -> None:
            must(run(privileged("systemctl") + ["restart", UNIT]), "systemctl restart")
            RESTART_PENDING.unlink(missing_ok=True)
        r.change(f"(re)start {UNIT}.service", restart_unit)
        return
    state, command, workdir = task_info()
    pythonw = python.with_name("pythonw.exe")
    # A task an older deploy or install.ps1 registered may run another copy (one inside a worktree)
    same = state != "absent" and [os.path.normcase(p) for p in (command, workdir)] == \
        [os.path.normcase(str(p)) for p in (pythonw, APP)]
    if same and state == "running" and not r.config_changed:
        r.already(f"scheduled task '{TASK}' installed and running")
        return
    if not same:
        def create() -> None:
            if state == "running":
                stop_task()
            with tempfile.TemporaryDirectory() as tmp:
                xml = Path(tmp) / "task.xml"
                xml.write_text(task_xml(str(pythonw)), encoding="utf-16")
                must(run([tool("schtasks"), "/Create", "/TN", TASK, "/XML", str(xml), "/F"]), "schtasks /Create")
        r.change(f"register scheduled task '{TASK}'" if state == "absent" else
                 f"register scheduled task '{TASK}' again to run {pythonw} in {APP} (it ran {command} in {workdir})",
                 create)

    def restart() -> None:
        stop_task()
        must(run([tool("schtasks"), "/Run", "/TN", TASK]), "schtasks /Run")
        RESTART_PENDING.unlink(missing_ok=True)
    r.change(f"(re)start scheduled task '{TASK}'", restart)


def remove_service(r: Run) -> None:
    r.step("Bridge service")
    if ts_install.PLATFORM == "darwin":
        r.already("no Bridge service on macOS (deploy does not install one there)")
        return
    if r.dry_run:
        what = f"{UNIT}.service" if TARGET == "linux" else f"scheduled task '{TASK}'"
        r.change(f"stop and remove {what}, if it is installed", lambda: None)
        return
    if service_state() == "absent":
        r.already("no Bridge service installed")
        return
    if TARGET == "linux":
        unit = SYSTEMD_DIR / f"{UNIT}.service"

        def remove() -> None:
            # A Bridge that is still running must not lose its unit, nor with --purge its config
            must(run(privileged("systemctl") + ["disable", "--now", UNIT]), "systemctl disable --now")
            must(run(privileged("rm") + ["-f", str(unit)]), "remove unit")
            must(run(privileged("systemctl") + ["daemon-reload"]), "daemon-reload")
        r.change(f"stop, disable and remove {UNIT}.service", remove)
        return

    def unregister() -> None:
        # A Bridge that is still running must not lose its task, nor with --purge its config
        stop_task()
        must(run([tool("schtasks"), "/Delete", "/TN", TASK, "/F"]), "schtasks /Delete")
    r.change(f"stop and remove scheduled task '{TASK}'", unregister)


# ---------------------------------------------------------------- firewall


def firewall_kind() -> str | None:
    if TARGET == "windows":
        return "netsh"
    for name in ("ufw", "firewall-cmd"):
        if shutil.which(name):
            return name
    return None


def rich_rule(subnet: str, port: int) -> str:
    family = "ipv6" if ":" in subnet else "ipv4"
    return f'rule family="{family}" source address="{subnet}" port port="{port}" protocol="tcp" accept'


def netsh_rule() -> str | None:
    """What netsh shows for the rule, or None when there is none by that name."""
    res = run([tool("netsh"), "advfirewall", "firewall", "show", "rule", f"name={RULE}"], timeout=30)
    return res.stdout if res.returncode == 0 else None


UFW_RULE_RE = re.compile(rf"^\s*(\d+)/tcp\s+ALLOW(?:\s+IN)?\s+(\S+)\s+#\s*{re.escape(RULE)}\s*$")


def ufw_rules() -> list[tuple[str, str]]:
    """(port, source) of every inbound TCP allow rule that carries this deployment's comment."""
    # A status that fails says nothing about the rules: it is not "no rule"
    res = must(run(privileged("ufw") + ["status"], timeout=30), "ufw status")
    return [(m.group(1), m.group(2)) for line in res.stdout.splitlines() if (m := UFW_RULE_RE.match(line))]


def firewalld_has(subnet: str, port: int, *, permanent: bool) -> bool:
    """Whether the rule is among firewalld's saved rules (permanent) or in the running firewall."""
    argv = privileged("firewall-cmd") + (["--permanent"] if permanent else [])
    res = run(argv + [f"--query-rich-rule={rich_rule(subnet, port)}"], timeout=30)
    if res.returncode not in (0, 1):  # 1 is "no"; anything else (252: firewalld is not running) is no answer
        must(res, "firewall-cmd --query-rich-rule")
    return res.returncode == 0


def firewall_present(kind: str, subnet: str, port: int) -> bool:
    if kind == "netsh":
        # The rule for THIS subnet and port: netsh's field names are localised, its values are not
        shown = netsh_rule()
        return (shown is not None and subnet in shown
                and re.search(rf"(?<![\d./]){port}(?![\d./])", shown) is not None)
    if kind == "ufw":
        return (str(port), subnet) in ufw_rules()
    # Saved only is not present: until a reload the running firewall still shuts the peers out
    return firewalld_has(subnet, port, permanent=True) and firewalld_has(subnet, port, permanent=False)


def step_firewall(r: Run, subnet: str, port: int) -> None:
    r.step(f"Firewall: port {port} from {subnet} only")
    kind = firewall_kind()
    if kind is None:
        out(f"  neither ufw nor firewalld found; allow port {port} only from {subnet} yourself, e.g.")
        out(f"    sudo ufw allow from {subnet} to any port {port} proto tcp")
        return
    if r.dry_run:  # reading ufw or firewalld needs root: a dry run asks neither
        r.change(f"{kind}: allow port {port} from {subnet} only, and delete any other rule of ours, unless "
                 "that is already so", lambda: None)
        return
    if kind == "ufw":
        rules = ufw_rules()
        # Ours by its comment, for another subnet or port: left in place it would keep that one open,
        # also beside the rule that is wanted
        stale = [rule for rule in rules if rule != (str(port), subnet)]
        if rules and not stale:
            r.already(f"{kind} rule for {subnet} on port {port}")
            return
        for old_port, old_subnet in stale:
            drop = privileged("ufw") + ["delete", "allow", "from", old_subnet, "to", "any", "port", old_port,
                                        "proto", "tcp"]
            r.change(f"delete the ufw rule for {old_subnet} on port {old_port}",
                     lambda drop=drop: must(run(drop), "ufw delete"))
        if (str(port), subnet) not in rules:
            argv = privileged("ufw") + ["allow", "from", subnet, "to", "any", "port", str(port), "proto", "tcp",
                                        "comment", RULE]
            r.change(f"ufw allow from {subnet} to port {port}", lambda: must(run(argv), "ufw allow"))
        return
    if kind == "firewall-cmd":
        saved = firewalld_has(subnet, port, permanent=True)
        if saved and firewalld_has(subnet, port, permanent=False):
            r.already(f"{kind} rule for {subnet} on port {port}")
            return
        if not saved:
            add = privileged("firewall-cmd") + ["--permanent", f"--add-rich-rule={rich_rule(subnet, port)}"]
            r.change(f"firewalld rule for {subnet} on port {port}",
                     lambda: must(run(add), "firewall-cmd --add-rich-rule"))
        # Also when an earlier run saved the rule and its reload failed
        r.change("firewall-cmd --reload (puts the saved rule into the running firewall)",
                 lambda: must(run(privileged("firewall-cmd") + ["--reload"]), "firewall-cmd --reload"))
        return
    if firewall_present(kind, subnet, port):
        r.already(f"{kind} rule for {subnet} on port {port}")
        return
    if netsh_rule() is not None:
        # Same name, another subnet or port: left in place it would keep that one open
        drop = [tool("netsh"), "advfirewall", "firewall", "delete", "rule", f"name={RULE}"]
        r.change(f"delete netsh rule '{RULE}', which is for another subnet or port",
                 lambda: must(run(drop), "netsh delete rule"))
    argv = [tool("netsh"), "advfirewall", "firewall", "add", "rule", f"name={RULE}", "dir=in", "action=allow",
            "protocol=TCP", f"localport={port}", f"remoteip={subnet}", "profile=private"]
    r.change(f"netsh rule '{RULE}' (private profile)", lambda: must(run(argv), "netsh add rule"))


def remove_firewall(r: Run, subnet: str, port: int) -> None:
    r.step("Firewall rule")
    if ts_install.PLATFORM == "darwin":
        r.already("no AI-Connect firewall rule on macOS (deploy does not add one there)")
        return
    kind = firewall_kind()
    if r.dry_run and kind is not None:
        r.change(f"delete the {kind} rule for the Bridge port, if there is one", lambda: None)
        return
    saved = running = False
    if kind == "firewall-cmd":
        saved, running = firewalld_has(subnet, port, permanent=True), firewalld_has(subnet, port, permanent=False)
    # Whatever its subnet or port: on Windows the rule is ours by name, with ufw by its comment
    present = kind is not None and (netsh_rule() is not None if kind == "netsh"
                                    else bool(ufw_rules()) if kind == "ufw"
                                    else saved or running)
    if not present:
        r.already("no AI-Connect firewall rule")
        return
    if kind == "netsh":
        argv = [tool("netsh"), "advfirewall", "firewall", "delete", "rule", f"name={RULE}"]
        r.change(f"delete netsh rule '{RULE}'", lambda: must(run(argv), "netsh delete rule"))
    elif kind == "ufw":
        for old_port, old_subnet in ufw_rules():
            argv = privileged("ufw") + ["delete", "allow", "from", old_subnet, "to", "any", "port", old_port,
                                        "proto", "tcp"]
            r.change(f"delete ufw rule for {old_subnet} on port {old_port}",
                     lambda argv=argv: must(run(argv), "ufw delete"))
    else:
        if saved:
            drop = privileged("firewall-cmd") + ["--permanent", f"--remove-rich-rule={rich_rule(subnet, port)}"]
            r.change(f"delete firewalld rule for {subnet} on port {port}",
                     lambda: must(run(drop), "firewall-cmd --remove-rich-rule"))
        # Also when an earlier run deleted the saved rule and its reload failed
        r.change("firewall-cmd --reload (takes the rule out of the running firewall)",
                 lambda: must(run(privileged("firewall-cmd") + ["--reload"]), "firewall-cmd --reload"))


# ---------------------------------------------------------------- claude code


def claude_bin() -> str | None:
    found = shutil.which("claude")
    if found:
        return found
    native = Path.home() / ".local" / "bin" / ("claude.exe" if os.name == "nt" else "claude")
    return str(native) if native.exists() else None


def plugin_installed(claude: str) -> bool:
    return PLUGIN_ID in run([claude, "plugin", "list"], timeout=60).stdout


def mcp_server_file() -> Path:
    return APP / "client" / "server.py"


def mcp_registered(claude: str, scope: str, python: Path) -> bool:
    """Registered as asked: this server file, under this venv's Python, in this scope ("Scope: User config
    ..." or "Scope: Project config ..." in `claude mcp get`; a line it does not print is not checked)."""
    res = run([claude, "mcp", "get", MCP_SERVER], timeout=60)
    if res.returncode != 0 or str(mcp_server_file()) not in res.stdout or str(python) not in res.stdout:
        return False
    line = next((ln.strip().lower() for ln in res.stdout.splitlines() if ln.strip().lower().startswith("scope:")), "")
    return not line or f"{scope} config" in line


HOOKS_WARNING = ("  WARNING: --install-hooks turns the plugin's hooks on for EVERY Claude Code session of this user "
                 "here (SessionStart, Stop, the peer-state hooks). A session in bypass-permissions mode then acts on "
                 "what another peer sends with no prompt in between. Leave it off on a shared machine.")
MCP_WARNING = ("  WARNING: --register-mcp gives Claude Code sessions ({where}) the ai-connect tools. What other peers "
               "send is untrusted input; in a bypass-permissions session nothing asks before the model acts on it.")


def step_claude(r: Run, args) -> None:
    """Nothing by default: a peer gets no hooks and no MCP server unless asked for each."""
    r.step("Claude Code")
    if not (args.install_hooks or args.register_mcp):
        r.record("skipped", "no plugin hooks and no MCP server (the default)")
        out("  skipped: no plugin hooks and no MCP server registered (the default). --register-mcp "
            "[--scope project|user] registers the MCP server, --install-hooks installs the plugin with its hooks")
        return
    claude = claude_bin()
    if claude is None:
        raise Failure("Claude Code (claude) not found; install it first: https://claude.com/claude-code")
    if args.install_hooks:
        out(HOOKS_WARNING)
        if r.dry_run:
            r.change(f"claude plugin install {PLUGIN_ID}, unless it is installed", lambda: None)
        elif plugin_installed(claude):
            r.already(f"plugin {PLUGIN_ID} installed")
        else:
            r.change(f"claude plugin install {PLUGIN_ID}",
                     lambda: must(run([claude, "plugin", "install", PLUGIN_ID]), "claude plugin install"))
    if not args.register_mcp:
        return
    where = ("scope user: every project of this user" if args.scope == "user"
             else f"scope project: sessions started in {Path.cwd()}, through its .mcp.json")
    out(MCP_WARNING.format(where=where))
    step_app(r, restart_on_change=False)
    python = venv_python() or VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    argv = [claude, "mcp", "add", "-s", args.scope, MCP_SERVER, "--", str(python), str(mcp_server_file())]
    if r.dry_run:
        r.change(f"register MCP server '{MCP_SERVER}' ({where}), unless it is registered", lambda: None)
        return
    if mcp_registered(claude, args.scope, python):
        r.already(f"MCP server '{MCP_SERVER}' registered ({where})")
        return

    def register() -> None:
        # A registration in this scope that points elsewhere (another venv, another checkout) is replaced
        run([claude, "mcp", "remove", "-s", args.scope, MCP_SERVER], timeout=60)
        must(run(argv, timeout=60), "claude mcp add")
    r.change(f"register MCP server '{MCP_SERVER}' ({where})", register)


def remove_claude(r: Run) -> None:
    r.step("Claude Code plugin and MCP server")
    claude = claude_bin()
    if claude is None:
        r.already("Claude Code not found, nothing registered there")
        return
    if r.dry_run:
        r.change(f"remove MCP server '{MCP_SERVER}' and plugin {PLUGIN_ID} from Claude Code, if registered",
                 lambda: None)
        return
    if run([claude, "mcp", "get", MCP_SERVER], timeout=60).returncode == 0:
        r.change(f"remove MCP server '{MCP_SERVER}'",
                 lambda: must(run([claude, "mcp", "remove", MCP_SERVER]), "claude mcp remove"))
    else:
        r.already(f"MCP server '{MCP_SERVER}' not registered")
    if plugin_installed(claude):
        r.change(f"claude plugin uninstall {PLUGIN_ID}",
                 lambda: must(run([claude, "plugin", "uninstall", PLUGIN_ID]), "claude plugin uninstall"))
    else:
        r.already(f"plugin {PLUGIN_ID} not installed")


# ---------------------------------------------------------------- bridge check


def verify(r: Run, what: str) -> None:
    r.step(what)
    if r.dry_run:
        out("  would: connect to the Bridge with this machine's peer token")
        return
    deadline = time.monotonic() + HEALTH_WAIT
    while True:
        result = config_tool("verify")
        if result.get("result") == "ok" or time.monotonic() >= deadline or result.get("result") == "refused":
            break
        time.sleep(1)
    if result.get("result") == "ok":
        out(f"  done: Bridge {result.get('url')} accepted this machine's token")
        return
    raise Failure(f"Bridge check: {result.get('detail') or result.get('result') or 'no answer'}")


# ---------------------------------------------------------------- commands


def coexistence(r: Run, accept_dns: bool) -> None:
    """No other VPN here may route Tailscale's addresses (tsadmin.vpn_coexistence): one line naming them."""
    if r.dry_run:
        out("  would: check that no other VPN here routes Tailscale's 100.64.0.0/10 or fd7a:115c:a1e0::/48")
        return
    out(f"  {tsadmin.vpn_coexistence('darwin' if ts_install.PLATFORM == 'darwin' else TARGET, accept_dns)}")


def step_own_key_expiry(r: Run) -> None:
    """This machine's node key made non-expiring. A node that joined by a login keeps an expiring key even
    once tagged (a tagged auth key would have turned expiry off), and drops off the tailnet when it runs out."""
    if r.dry_run:
        r.change("turn this machine's node key expiry off (with the stored OAuth client), unless it is off",
                 lambda: None)
        return
    me = ts_self()
    cid, secret, _source = tsadmin.stored_oauth_credentials()
    if not (cid and secret):
        if me.get("KeyExpiry"):
            out(f"  WARNING: this machine's node key expires {me['KeyExpiry']}, and the tailnet drops it then. "
                "Run `deploy tailnet-setup --apply` (it turns that off), or turn off key expiry for this machine "
                "in the admin console")
        else:
            r.already("this machine's node key does not expire")
        return
    node = str(me.get("ID") or "")
    try:
        token = tsadmin.access_token()
        dev = next((d for d in tsadmin.list_devices(token) if node and node in (d.get("nodeId"), d.get("id"))), None)
    except tsadmin.Failure as err:
        # The Bridge works without this; say so loudly rather than fail the whole deploy on it
        out(f"  WARNING: this machine's node key expiry could not be checked: {err}")
        return
    if dev is None:
        out(f"  WARNING: this machine (node {node or '?'}) is not in the tailnet's device list; key expiry unchecked")
    elif dev.get("keyExpiryDisabled"):
        r.already("this machine's node key expiry is off")
    else:
        r.change(f"turn this machine's node key expiry off (node {node})",
                 lambda: tsadmin.disable_key_expiry(token, dev))


def bridge_url(host: str, port: int) -> str:
    return f"ws://[{host}]:{port}" if ":" in host else f"ws://{host}:{port}"


def cmd_bridge(args) -> int:
    for peer in args.peer:
        check_name(peer, "--peer")
    check_name(args.name, "--name")
    if ts_install.PLATFORM == "darwin":
        raise Failure("a Bridge on macOS is not supported (deploy has no launchd service); run the Bridge on "
                      "Linux or Windows, and `deploy peer` here", EXIT_USAGE)
    r = Run(args.dry_run, total=7)
    out(f"=== AI-Connect deploy: bridge{' (dry run)' if r.dry_run else ''} ===")
    step_deps(r)

    r.step("Tailscale")
    coexistence(r, args.accept_dns)
    joined = ts_install.step_tailscale(r, not args.no_install_tailscale, args.accept_dns)
    if joined or r.dry_run:
        step_own_key_expiry(r)

    r.step("Configuration")
    # Only a dry run gets here without a tailnet address: it has said what it would do about that
    ip = tailscale_ip() if joined else "<this machine's Tailscale IPv4>"
    out(f"  Tailscale IPv4: {ip}")
    facts = inspect_config()
    if facts and facts.get("exists") and facts.get("host") == ip and facts.get("port") == args.port \
            and facts.get("bridge_url") == bridge_url(ip, args.port):
        r.already(f"{CONFIG_FILE} listens on {ip}:{args.port}")
    else:
        owe_restart(r)
        r.change(f"write {CONFIG_FILE} with server.host {ip}, port {args.port}",
                 lambda: config_tool("bridge", "--host", ip, "--port", str(args.port), "--name", args.name))
        facts = None if r.dry_run else inspect_config()

    r.step("Peer tokens")
    known = set((facts or {}).get("peers") or [])
    if not args.peer:
        out("  no --peer given; add one later with: deploy bridge --peer <name>")
    for peer in args.peer:
        target = TOKEN_DIR / f"{peer}.token"
        if peer in known and target.is_file():
            r.already(f"peer '{peer}' provisioned (token file: {target})")
            continue
        if peer in known:
            # The Bridge keeps only the hash: no file means the token cannot be handed out again
            r.already(f"peer '{peer}' provisioned, but its token file is not on this machine. For a new token: "
                      f"installer.py revoke-peer {peer}, then deploy bridge --peer {peer}")
            continue

        def provision(peer=peer, target=target) -> None:
            result = config_tool("add-peer", peer, "--out", str(target))
            out(f"  peer '{peer}' token {result.get('masked', '****')} written to {target}")
        owe_restart(r)
        r.change(f"provision peer '{peer}', token file {target}", provision)

    step_service(r)
    step_firewall(r, args.vpn_subnet, args.port)
    verify(r, "Health check")
    out("")
    out("Each peer needs its token file and a one-off auth key (vpn/mint-key.sh --name <peer> --out <file>), then:")
    out(f"  deploy peer --name <peer> --bridge {ip} --token-file <file> --auth-key-file <file>")
    return EXIT_OK


def read_peer_token(args, required: bool = True) -> str:
    if args.token_file:
        try:
            token = Path(args.token_file).read_text(encoding="utf-8").strip()
        except OSError as err:
            if not required:
                return ""
            raise Failure(f"cannot read token file {args.token_file}: {err.strerror}", EXIT_USAGE) from None
    else:
        token = os.environ.get("AI_CONNECT_PEER_TOKEN", "").strip() or own_token()
    if not token and required:
        raise Failure("no peer token: run `deploy peer ... --print-enrolment` first (the token then stays on this "
                      "machine), or pass --token-file, or set AI_CONNECT_PEER_TOKEN", EXIT_USAGE)
    tsadmin.remember_secret(token)
    return token


def own_token() -> str:
    """The token this peer generated for itself, or "" when it has none."""
    try:
        token = OWN_TOKEN.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    tsadmin.remember_secret(token)
    return token


def cmd_print_enrolment(args) -> int:
    """Make (once) this peer's own token and print {name, token_sha256}: what the Bridge needs, and no secret."""
    token = own_token()
    if not token:
        token = secrets.token_hex(32)
        tsadmin.remember_secret(token)
        write_own_token(token)
    print(json.dumps({"name": args.name, "token_sha256": hashlib.sha256(token.encode()).hexdigest()}), flush=True)
    print(f"deploy peer: the token itself stays in {OWN_TOKEN}. On the Bridge machine run: "
          f"deploy add-peer --name {args.name} --token-sha256 <token_sha256>", file=sys.stderr, flush=True)
    return EXIT_OK


def bridge_facts() -> dict:
    facts = inspect_config()
    if not (facts and facts.get("exists")):
        raise Failure(f"{CONFIG_FILE} missing: this machine is not a Bridge yet (run deploy bridge first)")
    return facts


def check_sha256(text: str | None) -> None:
    if text is not None and not SHA256_RE.match(text):
        raise Failure("--token-sha256 must be 64 lowercase hex characters (the token_sha256 that "
                      "`deploy join` or `deploy peer --print-enrolment` printed)", EXIT_USAGE)


def step_enrol(r: Run, name: str, sha256: str | None) -> None:
    """Let the peer in by its token hash; without a hash it has to be in already."""
    r.step("Peer enrolment by token hash")
    known = (bridge_facts().get("peer_sha256") or {}).get(name)
    if sha256 is None:
        if not known:
            raise Failure(f"peer '{name}' is not enrolled on this Bridge: pass --token-sha256, the hash "
                          "`deploy join` printed on that machine", EXIT_USAGE)
        r.already(f"peer '{name}' enrolled")
    elif known == sha256:
        r.already(f"peer '{name}' enrolled with this token hash")
    elif known:
        raise Failure(f"peer '{name}' is already provisioned with another token; to replace it: "
                      f"deploy remove --name {name} --yes (or installer.py revoke-peer {name}), then run this again")
    else:
        owe_restart(r)
        r.change(f"enrol peer '{name}' by its token hash ****{sha256[-4:]} in {CONFIG_FILE}",
                 lambda: config_tool("enrol", name, "--sha256", sha256))


def cmd_add_peer(args) -> int:
    check_name(args.name, "--name")
    check_sha256(args.token_sha256)
    r = Run(args.dry_run, total=2)
    out(f"=== AI-Connect deploy: add-peer '{args.name}'{' (dry run)' if r.dry_run else ''} ===")
    step_enrol(r, args.name, args.token_sha256)
    step_service(r)
    return EXIT_OK


def step_key_expiry(r: Run, name: str) -> None:
    """Node key expiry off for the peer's node: a node joined by a login keeps an expiring key even once
    tagged, and would drop off the tailnet when it runs out (180 days by default)."""
    r.step("Node key expiry")
    tag = tsadmin.DEFAULT_TAG
    if r.dry_run:  # asks the API nothing either
        r.change(f"turn key expiry off for node '{name}' ({tag}), unless it is off already", lambda: None)
        return
    token = tsadmin.access_token()
    matches = tsadmin.devices_named(tsadmin.list_devices(token), name, tag)
    if not matches:
        out(f"  no node '{name}' tagged {tag} on the tailnet yet: run this again once it has joined")
        return
    for dev in matches:
        label = f"node '{name}' ({tsadmin.device_id(dev)})"
        if dev.get("keyExpiryDisabled"):
            r.already(f"{label}: key expiry is off")
        else:
            r.change(f"turn key expiry off for {label}", lambda dev=dev: tsadmin.disable_key_expiry(token, dev))


def cmd_approve(args) -> int:
    """add-peer, the Bridge restart it needs, and the peer's node key made non-expiring."""
    check_name(args.name, "--name")
    check_sha256(args.token_sha256)
    r = Run(args.dry_run, total=3)
    out(f"=== AI-Connect deploy: approve '{args.name}'{' (dry run)' if r.dry_run else ''} ===")
    step_enrol(r, args.name, args.token_sha256)
    step_service(r)
    step_key_expiry(r, args.name)
    return EXIT_OK


def cmd_remove(args) -> int:
    """The peer's node off the tailnet, its token out of the Bridge, and the Bridge restarted."""
    check_name(args.name, "--name")
    if not args.yes and not args.dry_run:
        raise Failure("remove changes the tailnet and the Bridge: pass --yes (or --dry-run to preview)", EXIT_USAGE)
    facts = bridge_facts()
    if args.name == facts.get("name"):
        raise Failure(f"'{args.name}' is this Bridge's own peer: remove the Bridge with deploy uninstall", EXIT_USAGE)
    tag = tsadmin.DEFAULT_TAG
    r = Run(args.dry_run, total=3)
    out(f"=== AI-Connect deploy: remove '{args.name}'{' (dry run)' if r.dry_run else ''} ===")
    r.step("Tailnet node")
    if r.dry_run:
        r.change(f"delete node '{args.name}' ({tag}) from the tailnet, if it is there", lambda: None)
    else:
        token = tsadmin.access_token()
        matches = tsadmin.devices_named(tsadmin.list_devices(token), args.name, tag)
        if not matches:
            r.already(f"no node '{args.name}' tagged {tag} on the tailnet")
        for dev in matches:
            r.change(f"delete node {dev.get('name') or args.name} ({tsadmin.device_id(dev)}) from the tailnet",
                     lambda dev=dev: tsadmin.delete_device(token, dev))
    r.step("Bridge peer")
    token_file = TOKEN_DIR / f"{args.name}.token"
    if args.name in (facts.get("peers") or []):
        owe_restart(r)
        r.change(f"revoke peer '{args.name}' in {CONFIG_FILE}", lambda: config_tool("revoke", args.name))
    else:
        r.already(f"peer '{args.name}' is not provisioned on this Bridge")
    if token_file.exists():
        r.change(f"delete its token file {token_file}", token_file.unlink)
    step_service(r)
    return EXIT_OK


def cmd_list(_args) -> int:
    """The tailnet's nodes beside the Bridge's peers. The API lists no ephemeral flag, so none is shown."""
    token = tsadmin.access_token()
    devices = tsadmin.list_devices(token)
    facts = inspect_config() or {}
    bridge = bool(facts.get("exists") and facts.get("host"))
    peers, own = set(facts.get("peers") or []), facts.get("name")
    out("=== AI-Connect deploy: list ===")
    row = "  {:<20} {:<16} {:<22} {:<28} {:<30} {}"
    out(row.format("NAME", "IP", "TAGS", "ONLINE", "KEY EXPIRY", "BRIDGE"))
    expiring, names = [], set()
    for dev in sorted(devices, key=tsadmin.device_short_name):
        name = tsadmin.device_short_name(dev)
        names.add(name)
        ip = next((a for a in dev.get("addresses") or [] if ":" not in str(a)), "-")
        online = "yes" if dev.get("connectedToControl") else f"last seen {dev.get('lastSeen') or '?'}"
        if dev.get("keyExpiryDisabled"):
            expiry = "disabled"
        else:
            expiry = f"ENABLED, expires {dev.get('expires') or '?'}"
            expiring.append(name)
        role = ("this Bridge" if name == own else "peer" if name in peers else "not a Bridge peer") if bridge else "-"
        out(row.format(name, ip, ",".join(dev.get("tags") or []) or "-", online, expiry, role))
    for name in sorted(peers - names - {own}):
        out(row.format(name, "-", "-", "-", "-", "peer, not on the tailnet"))
    if not bridge:
        out("  (not a Bridge here: its peers are not shown)")
    if expiring:
        nodes = "1 node keeps" if len(expiring) == 1 else f"{len(expiring)} nodes keep"
        out(f"  {nodes} a key that expires: {', '.join(expiring)}. Turn it off: deploy approve --name <peer>, "
            "or deploy bridge for the Bridge itself")
    return EXIT_OK


def cmd_peer(args) -> int:
    check_name(args.name, "--name")
    check_host(args.bridge)
    if args.print_enrolment and args.dry_run:
        raise Failure("--print-enrolment makes this peer's token and has no dry run: it changes nothing else, "
                      "and nothing leaves this machine but the hash it prints", EXIT_USAGE)
    if args.print_enrolment:
        return cmd_print_enrolment(args)
    # A dry run needs neither the token nor the key, and asks no tool whether this machine is on the tailnet
    token = read_peer_token(args, required=not args.dry_run)
    on_tailnet = not args.dry_run and ts_install.installed() is not None and backend_state() == "Running"
    key_file = args.auth_key_file or os.environ.get("TS_AUTHKEY_FILE")
    if not args.dry_run and not on_tailnet and not key_file and not os.environ.get("TS_AUTHKEY", "").strip():
        raise Failure("not on the tailnet and no auth key: pass --auth-key-file or set TS_AUTHKEY")
    r = Run(args.dry_run, total=5)
    out(f"=== AI-Connect deploy: peer '{args.name}'{' (dry run)' if r.dry_run else ''} ===")
    if r.dry_run and not token:
        out("  note: no peer token here yet. `--print-enrolment` makes one, or pass --token-file")
    step_deps(r)
    step_claude(r, args)

    r.step("VPN (Tailscale)")
    coexistence(r, args.accept_dns)
    if on_tailnet:
        r.already("this machine is on the tailnet")
        ts_install.step_prefs(r, args.accept_dns)
    else:
        ts_install.step_install(r, not args.no_install_tailscale)
        step_join_with_key(r, args.name, args.accept_dns, key_file=args.auth_key_file)

    step_client_config(r, args.name, args.bridge, args.port, token)
    verify(r, "Bridge connection")
    return EXIT_OK


def step_join_with_key(r: Run, name: str, accept_dns: bool, *, key_file: str | None = None,
                       key: str | None = None) -> None:
    """Join the tailnet with a one-off auth key through vpn-up: from key_file, from key (handed over in the
    environment, never on a command line), else from TS_AUTHKEY / TS_AUTHKEY_FILE."""
    argv = [sys.executable, str(PLUGIN / "vpn" / "tsadmin.py"), "vpn-up", "--hostname", name]
    if key_file:
        argv += ["--auth-key-file", key_file]
    if accept_dns:
        argv.append("--accept-dns")
    up = ["tailscale", "up", "--auth-key=file:<owner-only copy of the one-off key>",
          f"--advertise-tags={tsadmin.DEFAULT_TAG}", *ts_install.pinned(accept_dns), f"--hostname={name}"]
    as_user = TARGET == "linux" and ts_install.PLATFORM == "linux" and not IS_ROOT
    out(f"    $ {'sudo ' if as_user else ''}{' '.join(up)}")

    def join_as_root() -> None:
        """tailscale up needs root on Linux (no operator is set on a fresh machine): through sudo, with the
        key in an owner-only file root reads. The config and the token stay this user's."""
        secret = key or ""
        source = key_file or os.environ.get("TS_AUTHKEY_FILE")
        if not secret and source:
            try:
                secret = Path(source).read_text(encoding="utf-8").strip()
            except OSError as err:
                raise Failure(f"cannot read the key file {source}: {err.strerror}", EXIT_USAGE) from None
        secret = secret or os.environ.get("TS_AUTHKEY", "").strip()
        if not secret:
            raise Failure("no auth key: pass --auth-key-file or set TS_AUTHKEY", EXIT_USAGE)
        tsadmin.remember_secret(secret)
        private_config_dir()
        held = CONFIG_DIR / f".join-key-{os.getpid()}"
        tsadmin.write_owner_only(held, secret + "\n")
        try:
            code = interactive([tool("sudo"), tsadmin.tailscale_bin(), "up", f"--auth-key=file:{held}", *up[3:]])
        finally:
            held.unlink(missing_ok=True)
        if code != 0:
            raise Failure(f"tailscale up failed (exit {code}): the key may be used or expired; make a new one")
        state = backend_state()
        if state != "Running":
            raise Failure("tailscale up returned, but this machine is not on the tailnet "
                          f"(state: {state or 'unknown'})")
        if key_file:
            Path(key_file).unlink(missing_ok=True)
            out(f"  used key file {key_file} deleted")

    def join() -> None:
        if as_user:
            join_as_root()
            return
        res = run(argv, timeout=300, env=dict(os.environ, TS_AUTHKEY=key) if key else None)
        for line in (res.stdout + res.stderr).strip().splitlines():
            out(f"  {line}")
        # 2 = joined, but vpn-up had no Bridge to probe; the last step checks the Bridge itself
        if res.returncode not in (tsadmin.EXIT_OK, tsadmin.EXIT_UNKNOWN):
            raise Failure(f"vpn-up failed (exit {res.returncode})")
        state = backend_state()
        if state != "Running":
            raise Failure(f"vpn-up returned, but this machine is not on the tailnet (state: {state or 'unknown'})")
    r.change(f"join the tailnet as '{name}' with the one-off auth key"
             + (", unless this machine is on it already (then pin its settings)" if r.dry_run else ""), join)


def step_client_config(r: Run, name: str, bridge: str, port: int, token: str) -> None:
    r.step("Client configuration")
    url = bridge_url(bridge, port)
    facts = inspect_config() or {}
    wanted = {"exists": True, "name": name, "bridge_url": url,
              "token_sha256": hashlib.sha256(token.encode()).hexdigest() if token else None}
    if token and all(facts.get(key) == value for key, value in wanted.items()):
        r.already(f"{CONFIG_FILE} points at {url} as '{name}' with this token")
    else:
        r.change(f"write {CONFIG_FILE}: client.name {name}, bridge {url}, token {mask(token)}",
                 lambda: config_tool("client", "--name", name, "--bridge", bridge, "--port", str(port),
                                     env_extra={"AI_CONNECT_PEER_TOKEN": token}))


# ---------------------------------------------------------------- invite and join


INVITE_PREFIX = "aic1."
INVITE_HELP = "not an ai-connect invite (expected the aic1. code that `deploy invite` made)"


def encode_invite(name: str, bridge: str, port: int, key: str) -> str:
    """aic1. and the base64url (no padding) of {v, name, bridge, port, key}: one line to paste or carry in a file."""
    raw = json.dumps({"v": 1, "name": name, "bridge": bridge, "port": port, "key": key}).encode()
    return INVITE_PREFIX + base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_invite(code: str) -> dict:
    """The invite's fields, checked. Never quotes the code: it holds a key."""
    code = code.strip()
    body = code[len(INVITE_PREFIX):] if code.startswith(INVITE_PREFIX) else ""
    try:
        invite = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))) if body else None
    except (ValueError, binascii.Error):
        invite = None
    ok = (isinstance(invite, dict) and invite.get("v") == 1
          and tsadmin.PEER_NAME_RE.match(str(invite.get("name", ""))) is not None
          and HOSTNAME_RE.match(str(invite.get("bridge", ""))) is not None
          and isinstance(invite.get("port"), int) and 1 <= invite["port"] <= 65535
          and str(invite.get("key", "")).startswith("tskey-auth-"))
    if not ok:
        raise Failure(INVITE_HELP, EXIT_USAGE)
    tsadmin.remember_secret(invite["key"])
    return invite


def cmd_invite(args) -> int:
    """A single-use, non-ephemeral, pre-approved tag:ai-peer key for one new machine, as an invite code."""
    check_name(args.name, "--name")
    if args.bridge:
        check_host(args.bridge)
    expiry = tsadmin.parse_expiry(args.expiry)
    tag, kind = tsadmin.DEFAULT_TAG, "ephemeral" if args.ephemeral else "not ephemeral"
    r = Run(args.dry_run, total=1)
    out(f"=== AI-Connect deploy: invite '{args.name}'{' (dry run)' if r.dry_run else ''} ===")
    r.step("Join key")
    where = f"write the invite owner-only to {args.out}" if args.out else "show the invite once"
    if r.dry_run:
        r.change(f"mint a single-use, {kind}, pre-approved {tag} key for '{args.name}' (expires in {args.expiry}) "
                 f"and {where}", lambda: None)
        return EXIT_OK
    bridge = args.bridge or tailscale_ip()
    port = args.port or (inspect_config() or {}).get("port") or DEFAULT_PORT  # this Bridge's own port
    key, expires = tsadmin.mint_auth_key(args.name, tag, expiry, args.ephemeral)
    code = encode_invite(args.name, bridge, port, key)
    tsadmin.remember_secret(code)
    what = f"invite for '{args.name}' (single use, {kind}, {tag}, Bridge {bridge}:{port}, expires {expires})"
    if args.out:
        tsadmin.write_owner_only(Path(args.out), code + "\n")
        r.record("done", what)
        out(f"  done: {what} written to {Path(args.out).resolve()}")
        out(f"  Carry that file to '{args.name}' and run there: deploy join --invite-file <file>")
    else:
        out(f"  {what}, shown once. It is a secret until it is used or expires:")
        print(f"  {code}", flush=True)  # the one deliberate secret on stdout: the admin asked for it
        out(f"  On '{args.name}': deploy join --invite, and paste it at the prompt "
            "(or put it in a file: --invite-file F, or in AI_CONNECT_INVITE)")
    out(f"  Then here: deploy approve --name {args.name} --token-sha256 <the hash join prints>")
    return EXIT_OK


def read_invite(args) -> dict | None:
    """The invite from --invite-file, AI_CONNECT_INVITE, or a hidden prompt (--invite); None without one."""
    if args.invite_file:
        try:
            code = Path(args.invite_file).read_text(encoding="utf-8")
        except OSError as err:
            raise Failure(f"cannot read the invite file {args.invite_file}: {err.strerror}", EXIT_USAGE) from None
    elif os.environ.get("AI_CONNECT_INVITE", "").strip():
        code = os.environ["AI_CONNECT_INVITE"]
    elif args.invite:
        if not has_terminal():
            raise Failure("--invite asks for the code, and there is no terminal here: pass --invite-file F or set "
                          "AI_CONNECT_INVITE", EXIT_USAGE)
        code = getpass.getpass("  Invite code (not shown): ")
    else:
        return None
    tsadmin.remember_secret(code.strip())
    return decode_invite(code)


def private_config_dir() -> None:
    """~/.config/ai-connect owner-only (0700): it holds this machine's token."""
    CONFIG_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != "nt":
        CONFIG_DIR.chmod(0o700)


def write_own_token(token: str) -> None:
    private_config_dir()
    tsadmin.write_owner_only(OWN_TOKEN, token + "\n")


def join_summary(bridge: str, port: int, name: str, digest: str) -> int:
    """VPN, port and token: PASS or FAIL, and PENDING for a token the Bridge has not been told about yet."""
    rows = [("VPN up", *smoke_test.check_vpn()), ("Bridge port reachable", *smoke_test.check_port(bridge, port))]
    auth = config_tool("verify")
    if auth.get("result") == "ok":
        rows.append(("Bridge accepts this token", True, f"{auth.get('url')} accepted this machine's token"))
    elif auth.get("result") == "refused":
        rows.append(("Bridge accepts this token", None, f"not approved yet: on the Bridge run deploy approve --name "
                                                        f"{name} --token-sha256 {digest}"))
    else:
        rows.append(("Bridge accepts this token", False, str(auth.get("detail") or auth.get("result") or "no answer")))
    width = max(len(title) for title, _ok, _detail in rows)
    out("")
    out(f"  {'CHECK'.ljust(width)}  RESULT   DETAIL")
    for title, ok, detail in rows:
        result = "PENDING" if ok is None else "PASS" if ok else "FAIL"
        out(f"  {title.ljust(width)}  {result.ljust(7)}  {detail}")
    if rows[-1][1]:
        out(f"  Joined and approved. The full end-to-end check: deploy test --bridge {bridge} --name {name}")
    return EXIT_FAILED if any(ok is False for _title, ok, _detail in rows) else EXIT_OK


def cmd_join(args) -> int:
    """A new machine in one command: Tailscale, the tailnet (invite or login), its own token, the client
    config, and a summary. Only the token's hash is printed, for `deploy approve` on the Bridge."""
    # A dry run asks for no secret and needs no file: the invite's fields are then shown as unknown
    unread = args.dry_run and not os.environ.get("AI_CONNECT_INVITE", "").strip() and (
        (args.invite and not args.invite_file) or (args.invite_file and not Path(args.invite_file).is_file()))
    invite = None if unread else read_invite(args)
    unknown = "<the invite's>"
    name = args.name or (invite or {}).get("name") or (unknown if unread else None)
    bridge = args.bridge or (invite or {}).get("bridge") or (unknown if unread else None)
    port = args.port or (invite or {}).get("port") or DEFAULT_PORT
    if invite and args.name and args.name != invite["name"]:
        raise Failure(f"--name {args.name} differs from the name the invite was made for ({invite['name']})",
                      EXIT_USAGE)
    if not (name and bridge):
        raise Failure("join needs --name and --bridge, or an invite that carries both (--invite-file F)", EXIT_USAGE)
    if name != unknown:
        check_name(name, "--name")
    if bridge != unknown:
        check_host(bridge)
    tag = tsadmin.DEFAULT_TAG
    r = Run(args.dry_run, total=6)
    out(f"=== AI-Connect deploy: join '{name}' to {bridge}:{port}{' (dry run)' if r.dry_run else ''} ===")

    r.step("Preflight")
    coexistence(r, args.accept_dns)
    if TARGET == "linux" and not IS_ROOT and shutil.which("sudo") is None:
        raise Failure("not root and no sudo: installing and starting Tailscale needs root; run this as root")
    out("  running as root" if IS_ROOT else "  sudo or Windows (UAC) asks where root or an administrator is needed")
    step_deps(r)

    r.step("Tailscale")
    ts_install.step_install(r, not args.no_install_tailscale)
    on_tailnet = not r.dry_run and ts_install.installed() is not None and backend_state() == "Running"
    if on_tailnet:
        r.already("this machine is on the tailnet")
        ts_install.step_prefs(r, args.accept_dns)
    elif invite or unread:
        step_join_with_key(r, name, args.accept_dns, key=(invite or {}).get("key"))
    else:
        ts_install.step_login(r, args.accept_dns, (f"--advertise-tags={tag}", f"--hostname={name}"))
        out(f"  joined by a login: `deploy approve --name {name}` on the Bridge also turns this node's key "
            "expiry off (an invite's key does that by itself)")
    if invite and args.invite_file and not r.dry_run and not on_tailnet:
        Path(args.invite_file).unlink(missing_ok=True)
        out(f"  used invite file {args.invite_file} deleted")

    r.step("Peer token")
    token = own_token()
    if token:
        r.already(f"this machine's own token is in {OWN_TOKEN}")
    else:
        token = secrets.token_hex(32)
        tsadmin.remember_secret(token)
        r.change(f"make this machine's own token, owner-only in {OWN_TOKEN}", lambda: write_own_token(token))
    step_client_config(r, name, bridge, port, token)
    step_claude(r, argparse.Namespace(install_hooks=args.with_hooks, register_mcp=args.register_mcp,
                                      scope=args.scope))
    digest = hashlib.sha256(token.encode()).hexdigest()
    if r.dry_run:
        out("  would: print this machine's enrolment {name, token_sha256} and check VPN, port and token")
        return EXIT_OK
    out("")
    print(json.dumps({"name": name, "token_sha256": digest}), flush=True)
    out(f"  The token stays here. On the Bridge: deploy approve --name {name} --token-sha256 {digest}")
    return join_summary(bridge, port, name, digest)


def cmd_status(args) -> int:
    out("=== AI-Connect deploy: status ===")
    python = venv_python()
    out(f"  installed files: {APP if (APP / 'server' / 'main.py').is_file() else 'missing'}")
    out(f"  venv: {('ok' if deps_ok(python) else 'dependencies missing') if python else 'missing'} ({VENV})")
    try:
        state = backend_state() or "unknown"
        ip = tailscale_ip() if state == "Running" else "-"
        out(f"  tailscale: {state}, IPv4 {ip}")
        if state == "Running":
            expires = ts_self().get("KeyExpiry")
            out(f"  node key: EXPIRES {expires}, and the tailnet drops this machine then. Turn it off: on the Bridge, "
                "deploy approve --name <this peer> (deploy bridge, if this is the Bridge)" if expires
                else "  node key: does not expire")
        prefs = ts_prefs()
        if prefs is None:
            out("  tailscale settings: unknown (tailscale debug prefs did not answer)")
        else:
            exit_node = prefs.get("ExitNodeID") or prefs.get("ExitNodeIP") or "none"
            line = (f"  tailscale settings: RouteAll {str(bool(prefs.get('RouteAll'))).lower()}, "
                    f"ExitNode {exit_node}, CorpDNS {str(bool(prefs.get('CorpDNS'))).lower()}")
            wrong = ts_install.unpinned(prefs, accept_dns=False)
            if wrong:
                line += (" - ON: it " + "; ".join(wrong) + ". Another VPN can lose its routes or DNS to it; "
                         "`tailscale set --accept-routes=false --exit-node= --accept-dns=false` turns them off")
            out(line)
    except (Failure, tsadmin.Failure) as err:
        out(f"  tailscale: {err}")
    facts = inspect_config() if python else None
    if facts and facts.get("exists"):
        out(f"  config: {CONFIG_FILE} (server.host {facts.get('host')}, bridge {facts.get('bridge_url')}, "
            f"{len(facts.get('peers') or [])} peer(s))")
    else:
        out(f"  config: {'missing' if python else 'unknown (no venv)'}")
    try:
        out(f"  service: {service_state()}")
    except Failure as err:
        out(f"  service: unknown ({err})")
    kind = firewall_kind()
    port = (facts or {}).get("port") or DEFAULT_PORT
    if kind in ("ufw", "firewall-cmd") and not IS_ROOT:
        # status runs nothing through sudo; reading either firewall needs root
        how = "sudo ufw status" if kind == "ufw" else "sudo firewall-cmd --list-rich-rules"
        out(f"  firewall: not checked ({kind} needs root, and status runs nothing through sudo: {how})")
    else:
        try:
            present = kind is not None and firewall_present(kind, args.vpn_subnet, port)
            found = f"rule present for {args.vpn_subnet} on port {port}" if present else "no rule"
            out(f"  firewall: {found if kind else 'no ufw/firewalld'}")
        except Failure as err:
            out(f"  firewall: unknown ({err})")
    # No claude command either: it may update itself or reach the network. `claude mcp get ai-connect` shows it
    out("  claude code: not checked (status runs no claude command; `claude mcp get ai-connect` and "
        "`claude plugin list` show what is registered)")
    if facts and facts.get("exists"):
        result = config_tool("verify")
        out(f"  bridge: {result.get('result')}{' - ' + result['detail'] if result.get('detail') else ''}")
    return EXIT_OK


def cmd_uninstall(args) -> int:
    if not args.yes and not args.dry_run:
        raise Failure("uninstall changes this machine: pass --yes (or --dry-run to preview)", EXIT_USAGE)
    r = Run(args.dry_run, total=4)
    out(f"=== AI-Connect deploy: uninstall{' (dry run)' if r.dry_run else ''} ===")
    remove_service(r)
    remove_firewall(r, args.vpn_subnet, args.port)
    remove_claude(r)
    r.step("Configuration and installed files")
    # Only what deploy made there: an AI_CONNECT_HOME pointed at a busier directory keeps everything else
    # The venv only when it is deploy's own: the default place, unmoved by AI_CONNECT_VENV, and a venv
    ours = APP_HOME / "venv"
    installed = [APP] if (APP / ".claude-plugin" / "plugin.json").is_file() and (APP / "server").is_dir() else []
    if VENV == ours and (ours / "pyvenv.cfg").is_file():
        installed.append(ours)
    if not args.purge:
        out(f"  kept: {CONFIG_DIR} and {APP_HOME} (pass --purge to delete them, the tokens with them)")
    else:
        for path in (CONFIG_DIR, APP_HOME):
            if path == APP_HOME and installed:
                def purge_app() -> None:
                    for each in installed:
                        shutil.rmtree(each)
                    if not any(APP_HOME.iterdir()):
                        APP_HOME.rmdir()
                r.change(f"delete {' and '.join(map(str, installed))}", purge_app)
            elif path == CONFIG_DIR and path.exists():
                r.change(f"delete {CONFIG_DIR}", lambda: shutil.rmtree(CONFIG_DIR))
            else:
                r.already(f"{path} not there" if path == CONFIG_DIR else f"no installed files in {APP_HOME}")
    out("The tailnet membership stays; leave the tailnet with vpn/vpn-down.sh --logout.")
    return EXIT_OK


# ---------------------------------------------------------------- entry


def check_name(name: str, flag: str) -> None:
    if not tsadmin.PEER_NAME_RE.match(name):
        raise Failure(f"{flag} '{name}' must be 1-63 letters, digits or hyphens", EXIT_USAGE)


def check_host(host: str) -> None:
    if not HOSTNAME_RE.match(host):
        raise Failure(f"--bridge '{host}' is not an IP address or host name", EXIT_USAGE)


def port_arg(text: str) -> int:
    try:
        port = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a port: {text}") from None
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError(f"not a port: {text}")
    return port


def subnet_arg(text: str) -> str:
    try:
        return str(ipaddress.ip_network(text, strict=True))
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a subnet: {text}") from None


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="deploy", description=__doc__.split("\n\n", maxsplit=1)[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("bridge", help="this machine runs the Bridge")
    b.add_argument("--name", default=re.sub(r"[^A-Za-z0-9-]", "-", socket.gethostname())[:63] or "bridge",
                   help="this machine's own peer name (default: host name)")
    b.add_argument("--peer", action="append", default=[], help="provision a token for this peer (repeatable)")
    b.set_defaults(func=cmd_bridge)

    pe = sub.add_parser("peer", help="this machine joins a Bridge")
    pe.add_argument("--name", required=True, help="this peer's name, as provisioned on the Bridge")
    pe.add_argument("--bridge", required=True, help="the Bridge's Tailscale IP or name")
    pe.add_argument("--auth-key-file", help="one-off Tailscale auth key file (or TS_AUTHKEY); deleted after use")
    pe.add_argument("--token-file", help="this peer's token file from the Bridge (or AI_CONNECT_PEER_TOKEN; "
                                         "default: the token --print-enrolment made)")
    pe.add_argument("--print-enrolment", action="store_true",
                    help="only make this peer's own token and print {name, token_sha256} for `deploy add-peer`")
    pe.add_argument("--register-mcp", action="store_true",
                    help="also register the ai-connect MCP server with Claude Code (off by default)")
    pe.add_argument("--scope", choices=("project", "user"), default="project",
                    help="where --register-mcp registers it: this directory's .mcp.json (project, the default) or "
                         "every project of this user (user)")
    pe.add_argument("--install-hooks", action="store_true",
                    help="also install the plugin with its hooks for every Claude Code session here (off by default)")
    pe.set_defaults(func=cmd_peer)

    a = sub.add_parser("add-peer", help="on the Bridge: let in a peer that made its own token, by the token's hash")
    a.add_argument("--name", required=True, help="the peer's name")
    a.add_argument("--token-sha256", required=True, help="token_sha256 from `deploy peer --print-enrolment`")
    a.add_argument("--dry-run", action="store_true", help="print what would change, change nothing")
    a.set_defaults(func=cmd_add_peer)

    iv = sub.add_parser("invite", help="on the Bridge: a single-use, non-ephemeral join key for one new machine")
    iv.add_argument("--name", required=True, help="the new machine's peer name")
    iv.add_argument("--bridge", help="the Bridge address the invite carries (default: this machine's Tailscale IPv4)")
    iv.add_argument("--port", type=port_arg, default=None, help="Bridge port (default: this Bridge's, else 9999)")
    iv.add_argument("--expiry", default="1h", help="how long the invite can be used: 1h (default), 30m, 1d")
    iv.add_argument("--ephemeral", action="store_true",
                    help="the node is removed soon after it goes offline: throwaway or CI machines only")
    iv.add_argument("--out", help="write the invite owner-only to this file (default: show it once)")
    iv.add_argument("--dry-run", action="store_true", help="print what would change, change nothing")
    iv.set_defaults(func=cmd_invite)

    jn = sub.add_parser("join", help="a new machine: Tailscale, the tailnet, its own token and the client config")
    jn.add_argument("--invite-file", help="the invite `deploy invite --out` wrote (deleted once used)")
    jn.add_argument("--invite", action="store_true", help="ask for the invite code (hidden); or AI_CONNECT_INVITE")
    jn.add_argument("--name", help="this machine's peer name (default: the invite's)")
    jn.add_argument("--bridge", help="the Bridge's Tailscale IP (default: the invite's)")
    jn.add_argument("--port", type=port_arg, default=None, help="Bridge port (default: the invite's, else 9999)")
    jn.add_argument("--with-hooks", action="store_true",
                    help="also install the plugin with its hooks for every Claude Code session here (off by default)")
    jn.add_argument("--register-mcp", action="store_true", help="also register the MCP server (off by default)")
    jn.add_argument("--scope", choices=("project", "user"), default="project", help="where --register-mcp goes")
    jn.add_argument("--accept-dns", action="store_true", help="let Tailscale manage DNS (off: another VPN keeps it)")
    jn.add_argument("--no-install-tailscale", action="store_true", help="fail (exit 3) instead of installing it")
    jn.add_argument("--dry-run", action="store_true", help="print what would change, change nothing")
    jn.set_defaults(func=cmd_join)

    ap = sub.add_parser("approve", help="on the Bridge: let a joined machine in (add-peer, restart, key expiry off)")
    ap.add_argument("--name", required=True, help="the peer's name")
    ap.add_argument("--token-sha256", help="token_sha256 that `deploy join` printed (not needed once enrolled)")
    ap.add_argument("--dry-run", action="store_true", help="print what would change, change nothing")
    ap.set_defaults(func=cmd_approve)

    rm = sub.add_parser("remove", help="on the Bridge: take a peer off the tailnet and out of the Bridge")
    rm.add_argument("--name", required=True, help="the peer's name")
    rm.add_argument("--yes", action="store_true", help="really do it")
    rm.add_argument("--dry-run", action="store_true", help="print what would change, change nothing")
    rm.set_defaults(func=cmd_remove)

    ls = sub.add_parser("list", help="the tailnet's nodes beside this Bridge's peers, and any key that expires")
    ls.set_defaults(func=cmd_list)

    s = sub.add_parser("status", help="show what is deployed here")
    s.set_defaults(func=cmd_status)

    u = sub.add_parser("uninstall", help="remove the service, firewall rule and Claude Code registration")
    u.add_argument("--yes", action="store_true", help="really do it")
    u.add_argument("--purge", action="store_true", help="also delete ~/.config/ai-connect (config and tokens)")
    u.set_defaults(func=cmd_uninstall)

    for cmd in (b, pe, u):
        cmd.add_argument("--dry-run", action="store_true", help="print what would change, change nothing")
        cmd.add_argument("--port", type=port_arg, default=DEFAULT_PORT, help="Bridge port (default 9999)")
    for cmd in (b, pe):
        cmd.add_argument("--accept-dns", action="store_true",
                         help="let Tailscale manage this machine's DNS (MagicDNS); off by default, because it "
                              "collides with a VPN client or DNS hook that is already there")
        cmd.add_argument("--no-install-tailscale", action="store_true",
                         help="fail (exit 3) instead of installing Tailscale when it is missing")
    for cmd in (b, u, s):
        cmd.add_argument("--vpn-subnet", type=subnet_arg, default=DEFAULT_SUBNET,
                         help="only this range may reach the port (default Tailscale's 100.64.0.0/10)")
    tailnet_setup.add_parser(sub)
    smoke_test.add_parser(sub, port_arg, check_name, check_host)
    return p


def main(argv: list[str] | None = None) -> int:
    if sys.version_info < (3, 10):
        print("deploy: Python 3.10 or newer is required", file=sys.stderr)
        return EXIT_FAILED
    if TARGET not in ("linux", "windows"):
        print(f"deploy: AI_CONNECT_DEPLOY_OS must be linux or windows, not {TARGET}", file=sys.stderr)
        return EXIT_USAGE
    args = build_parser().parse_args(argv)
    if getattr(args, "dry_run", False):
        no_tools()
    try:
        return args.func(args)
    except (Failure, tsadmin.Failure) as err:
        print(tsadmin.redact(f"deploy {args.cmd}: {err}"), file=sys.stderr, flush=True)
        return err.code
    except Exception as err:  # pylint: disable=broad-exception-caught  # never let a traceback carry a secret
        print(tsadmin.redact(f"deploy {args.cmd}: unexpected {type(err).__name__}: {err}"), file=sys.stderr)
        return EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
