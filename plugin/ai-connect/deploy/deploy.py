#!/usr/bin/env python3
"""AI-Connect deploy: one core behind the deploy.sh / deploy.ps1 pair.

  deploy bridge [--name N] [--peer P ...] [--port N] [--vpn-subnet CIDR] [--dry-run]
  deploy peer --name N --bridge HOST [--port N] [--auth-key-file F] [--token-file F] [--dry-run]
              [--register-mcp [--scope project|user]] [--install-hooks]      both off by default
  deploy peer --name N --bridge HOST --print-enrolment      make this peer's own token, print only its hash
  deploy add-peer --name N --token-sha256 HEX [--dry-run]   on the Bridge: let that peer in by the hash
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
                         EXIT_OK, EXIT_USAGE, IS_ROOT, PLUGIN, VENV, Failure, Run, backend_state, config_tool, mask, must,
                         no_tools, out,
                         privileged, run, tailscale_ip, tool, ts_prefs, tsadmin, venv_python)

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


def deps_ok(python: Path) -> bool:
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
    r.change(f"install this checkout's files to {APP} ({what})", sync)
    if have and restart_on_change:
        owe_restart(r)  # a running Bridge still has the old code loaded


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


def mcp_registered(claude: str) -> bool:
    res = run([claude, "mcp", "get", MCP_SERVER], timeout=60)
    return res.returncode == 0 and str(mcp_server_file()) in res.stdout


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
    if mcp_registered(claude):
        r.already(f"MCP server '{MCP_SERVER}' registered")
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
        tsadmin.write_owner_only(OWN_TOKEN, token + "\n")
    print(json.dumps({"name": args.name, "token_sha256": hashlib.sha256(token.encode()).hexdigest()}), flush=True)
    print(f"deploy peer: the token itself stays in {OWN_TOKEN}. On the Bridge machine run: "
          f"deploy add-peer --name {args.name} --token-sha256 <token_sha256>", file=sys.stderr, flush=True)
    return EXIT_OK


def cmd_add_peer(args) -> int:
    check_name(args.name, "--name")
    if not SHA256_RE.match(args.token_sha256):
        raise Failure("--token-sha256 must be 64 lowercase hex characters (the token_sha256 that "
                      "`deploy peer --print-enrolment` printed)", EXIT_USAGE)
    r = Run(args.dry_run, total=2)
    out(f"=== AI-Connect deploy: add-peer '{args.name}'{' (dry run)' if r.dry_run else ''} ===")
    r.step("Peer enrolment by token hash")
    facts = inspect_config()
    if not (facts and facts.get("exists")):
        raise Failure(f"{CONFIG_FILE} missing: this machine is not a Bridge yet (run deploy bridge first)")
    known = (facts.get("peer_sha256") or {}).get(args.name)
    if known == args.token_sha256:
        r.already(f"peer '{args.name}' enrolled with this token hash")
    elif known:
        raise Failure(f"peer '{args.name}' is already provisioned with another token; to replace it: "
                      f"installer.py revoke-peer {args.name}, then run this again")
    else:
        owe_restart(r)
        r.change(f"enrol peer '{args.name}' by its token hash ****{args.token_sha256[-4:]} in {CONFIG_FILE}",
                 lambda: config_tool("enrol", args.name, "--sha256", args.token_sha256))
    step_service(r)
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
        argv = [sys.executable, str(PLUGIN / "vpn" / "tsadmin.py"), "vpn-up", "--hostname", args.name]
        if args.auth_key_file:
            argv += ["--auth-key-file", args.auth_key_file]
        if args.accept_dns:
            argv.append("--accept-dns")
        out(f"    $ tailscale up --auth-key=file:<owner-only copy of the one-off key> "
            f"--advertise-tags={tsadmin.DEFAULT_TAG} {' '.join(ts_install.pinned(args.accept_dns))} "
            f"--hostname={args.name}")

        def join() -> None:
            res = run(argv, timeout=300)
            for line in (res.stdout + res.stderr).strip().splitlines():
                out(f"  {line}")
            # 2 = joined, but vpn-up had no Bridge to probe; the last step checks the Bridge itself
            if res.returncode not in (tsadmin.EXIT_OK, tsadmin.EXIT_UNKNOWN):
                raise Failure(f"vpn-up failed (exit {res.returncode})")
            state = backend_state()
            if state != "Running":
                raise Failure(f"vpn-up returned, but this machine is not on the tailnet (state: {state or 'unknown'})")
        r.change(f"join the tailnet as '{args.name}' with the one-off auth key"
                 + (", unless this machine is on it already (then pin its settings)" if r.dry_run else ""), join)

    r.step("Client configuration")
    url = bridge_url(args.bridge, args.port)
    facts = inspect_config() or {}
    wanted = {"exists": True, "name": args.name, "bridge_url": url,
              "token_sha256": hashlib.sha256(token.encode()).hexdigest() if token else None}
    if token and all(facts.get(key) == value for key, value in wanted.items()):
        r.already(f"{CONFIG_FILE} points at {url} as '{args.name}' with this token")
    else:
        r.change(f"write {CONFIG_FILE}: client.name {args.name}, bridge {url}, token {mask(token)}",
                 lambda: config_tool("client", "--name", args.name, "--bridge", args.bridge, "--port", str(args.port),
                                     env_extra={"AI_CONNECT_PEER_TOKEN": token}))

    verify(r, "Bridge connection")
    return EXIT_OK


def cmd_status(args) -> int:
    out("=== AI-Connect deploy: status ===")
    python = venv_python()
    out(f"  installed files: {APP if (APP / 'server' / 'main.py').is_file() else 'missing'}")
    out(f"  venv: {('ok' if deps_ok(python) else 'dependencies missing') if python else 'missing'} ({VENV})")
    try:
        state = backend_state() or "unknown"
        ip = tailscale_ip() if state == "Running" else "-"
        out(f"  tailscale: {state}, IPv4 {ip}")
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
    installed = [p for p in (APP, APP_HOME / "venv") if p.exists()]
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
