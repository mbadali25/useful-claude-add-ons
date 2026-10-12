"""Stand-in for every system tool deploy.py drives: one program, the tool's name as argv[1].

tailscale, sudo, tee, rm, systemctl, ufw, firewall-cmd, schtasks, powershell, netsh,
claude, and the Tailscale
installers curl, sh, install, apt-get, winget, msiexec and brew. State is the
JSON file in $FAKE_DEPLOY_STATE; every call's argv is appended to $FAKE_DEPLOY_LOG,
one JSON list per line. Nothing outside those two files and the paths a test
hands it is ever touched.

State keys: ts_ip, ts_backend, units {name: {active, enabled}}, ufw [lines],
tasks {name: status}, rules {name: remoteip}, plugins [ids], mcp {name: argv},
rule_ports {name: localport}, disable_rc / restart_rc (exit code of systemctl disable / restart),
end_rc (exit code of schtasks /End), end_noop (/End succeeds and the task runs on),
task_state_rc (exit code of the PowerShell task-state query), ufw_status_rc (exit code of
ufw status), fw_permanent / fw_runtime [rich rules], reload_rc (exit code of firewall-cmd
--reload), prefs {RouteAll, ExitNodeID, CorpDNS} (tailscale debug prefs; up and set change them),
vpns [{name, routes}] (other VPN interfaces, for ip and Get-NetAdapter), vpn_probe_rc,
noise (tailscale ip -4 also writes a byte that is neither cp1252 nor UTF-8),
after_up (BackendState after `tailscale up`), ts_node_id, install_rc (exit code of an installer),
shim (the launcher text an installer writes as the tailscale command into $FAKE_DEPLOY_BIN).
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def load() -> dict:
    return json.loads(Path(os.environ["FAKE_DEPLOY_STATE"]).read_text(encoding="utf-8"))


def save(state: dict) -> None:
    text = json.dumps(state)  # build the payload before the write truncates the file
    Path(os.environ["FAKE_DEPLOY_STATE"]).write_text(text, encoding="utf-8")


PREFS = {"--accept-routes": "RouteAll", "--accept-dns": "CorpDNS"}


def set_prefs(args, state) -> None:
    prefs = state.setdefault("prefs", {})
    for arg in args:
        flag, _, value = arg.partition("=")
        if flag in PREFS:
            prefs[PREFS[flag]] = value == "true"
        elif flag == "--exit-node":
            prefs["ExitNodeID"] = value


def tailscale(args, state):
    if args[:2] == ["ip", "-4"]:
        if not state.get("ts_ip"):
            print("no current Tailscale IPs; state: Stopped", file=sys.stderr)
            return 1
        print(state["ts_ip"], flush=True)
        if state.get("noise"):
            # A byte that is neither cp1252 nor UTF-8: what a localised tool can write
            sys.stdout.buffer.write(b"\x9d\n")
        return 0
    if args and args[0] == "status":
        me = {"ID": state.get("ts_node_id", "nFAKENODE11CNTRL")}
        if state.get("ts_key_expiry"):  # as tailscale prints it: KeyExpiry only while the key expires
            me["KeyExpiry"] = state["ts_key_expiry"]
        print(json.dumps({"BackendState": state.get("ts_backend", "Running"), "Self": me}))
        return 0
    if args[:2] == ["debug", "prefs"]:
        print(json.dumps({"RouteAll": False, "ExitNodeID": "", "CorpDNS": False, **state.get("prefs", {})}))
        return 0
    if args and args[0] in ("up", "set"):
        set_prefs(args[1:], state)
        for arg in args:
            if arg.startswith("--auth-key=file:"):  # what tailscale itself does with it: read the file
                key = Path(arg.removeprefix("--auth-key=file:")).read_text(encoding="utf-8").strip()
                state["up_key_sha256"] = hashlib.sha256(key.encode()).hexdigest()
        if args[0] == "up":
            state["ts_backend"] = state.get("after_up", "Running")
            state["ts_ip"] = state.get("ts_ip") or "127.0.0.1"
        save(state)
        return 0
    return 64


def ip(args, state):
    """`ip -j link show up` and `ip -j [-6] route show table all`, from state vpns [{name, routes}]."""
    if state.get("vpn_probe_rc"):
        return int(state["vpn_probe_rc"])
    vpns = state.get("vpns", [])
    if args[1:] == ["link", "show", "up"]:
        print(json.dumps([{"ifname": "lo"}, {"ifname": "eth0"}, {"ifname": "tailscale0"}]
                         + [{"ifname": v["name"]} for v in vpns]))
        return 0
    six = "-6" in args
    print(json.dumps([{"dst": "default", "dev": "eth0"}, {"dst": "100.64.0.0/10", "dev": "tailscale0"}]
                     + [{"dst": "default" if r in ("0.0.0.0/0", "::/0") else r, "dev": v["name"]}
                        for v in vpns for r in v["routes"] if (":" in r) == six]))
    return 0


def install_tailscale(state) -> int:
    """What every installer does here: put the tailscale command on the fake PATH, logged out."""
    if state.get("install_rc"):
        return int(state["install_rc"])
    name = "tailscale.cmd" if os.name == "nt" else "tailscale"
    path = Path(os.environ["FAKE_DEPLOY_BIN"]) / name
    path.write_bytes(state["shim"].replace("{name}", "tailscale").encode("utf-8"))
    path.chmod(0o755)
    state["ts_backend"], state["ts_ip"] = "NeedsLogin", ""
    save(state)
    print("fake installer: unpacking tailscale ...")  # a real one is chatty on stdout
    return 0


def curl(args, state):
    # curl_404: a part of the URL the server does not have (curl -f exits 22)
    if state.get("curl_404") and any(state["curl_404"] in arg for arg in args):
        print("curl: (22) The requested URL returned error: 404", file=sys.stderr)
        return 22
    if state.get("curl_rc"):  # e.g. 6, could not resolve the host: no network
        print(f"curl: ({state['curl_rc']}) Could not resolve host", file=sys.stderr)
        return int(state["curl_rc"])
    Path(args[args.index("-o") + 1]).write_text("# fake download\n", encoding="utf-8")
    return 0


def install(_args, _state):
    return 0  # the real one would copy a file into /usr/share or /etc: never here


def apt_get(args, state):
    if args[:1] == ["update"]:
        return 0
    if state.get("apt_rc"):  # e.g. 100, another apt or dpkg holds the lock
        print("E: Could not get lock /var/lib/dpkg/lock-frontend", file=sys.stderr)
        return int(state["apt_rc"])
    return install_tailscale(state) if args[:3] == ["install", "-y", "tailscale"] else 64


def sh(_args, state):
    return install_tailscale(state)


def winget(args, state):
    return install_tailscale(state) if args[:1] == ["install"] else 64


def msiexec(_args, state):
    return install_tailscale(state)


def brew(args, state):
    # The renamed cask is the one this Homebrew knows
    if args[:2] != ["install", "--cask"] or args[2] != state.get("brew_cask", "tailscale-app"):
        return 1
    return install_tailscale(state)


def sudo(args, _state):
    if args and args[0] == "-n":
        args = args[1:]
    found = shutil.which(args[0])
    return subprocess.run([found, *args[1:]], check=False).returncode


def tee(args, _state):
    data = sys.stdin.read()
    Path(args[-1]).write_text(data, encoding="utf-8", newline="\n")
    return 0


def rm(args, _state):
    for arg in args:
        if not arg.startswith("-"):
            Path(arg).unlink(missing_ok=True)
    return 0


def systemctl(args, state):
    units = state.setdefault("units", {})
    verb, name = args[0], (args[-1] if len(args) > 1 else "")
    unit = units.setdefault(name, {"active": False, "enabled": False}) if name else {}
    if verb == "is-active":
        print("active" if unit["active"] else "inactive")
        return 0 if unit["active"] else 3
    if verb == "is-enabled":
        print("enabled" if unit["enabled"] else "disabled")
        return 0 if unit["enabled"] else 1
    if verb in ("restart", "start"):
        if state.get("restart_rc"):
            print("Failed to restart unit: Access denied", file=sys.stderr)
            return int(state["restart_rc"])
        unit["active"] = True
    elif verb == "enable":
        unit["enabled"] = True
    elif verb == "disable":
        if state.get("disable_rc"):
            print("Failed to disable unit: Access denied", file=sys.stderr)
            return int(state["disable_rc"])
        unit["enabled"] = False
        unit["active"] = unit["active"] and "--now" not in args
    elif verb != "daemon-reload":
        return 64
    save(state)
    return 0


def ufw(args, state):
    rules = state.setdefault("ufw", [])
    if args[0] == "status":
        if state.get("ufw_status_rc"):
            print("ERROR: You need to be root to run this script", file=sys.stderr)
            return int(state["ufw_status_rc"])
        print("Status: active\n\nTo                         Action      From")
        print("--                         ------      ----")
        print("\n".join(rules))
        return 0
    delete = args[0] == "delete"
    words = args[1:] if delete else args
    subnet, port = words[words.index("from") + 1], words[words.index("port") + 1]
    line = f"{port}/tcp                   ALLOW       {subnet}              # AI-Connect Bridge"
    if delete:
        rules.remove(line)
    else:
        rules.append(line)
    save(state)
    return 0


def firewall_cmd(args, state):
    permanent, runtime = state.setdefault("fw_permanent", []), state.setdefault("fw_runtime", [])
    if args == ["--reload"]:
        if state.get("reload_rc"):
            print("Error: INVALID_ZONE: another zone's file is broken", file=sys.stderr)
            return int(state["reload_rc"])
        state["fw_runtime"] = list(permanent)
        save(state)
        return 0
    rules = permanent if "--permanent" in args else runtime
    verb, _, rule = args[-1].partition("=")
    if verb == "--query-rich-rule":
        print("yes" if rule in rules else "no")
        return 0 if rule in rules else 1
    if verb == "--add-rich-rule":
        rules.append(rule)
    elif verb == "--remove-rich-rule":
        rules.remove(rule)
    else:
        return 64
    save(state)
    return 0


def powershell(args, state):
    """The scheduled-task state query (the state as a number, never as a word in some language), and the
    list of other VPN adapters that are up (state vpns [{name, routes}])."""
    if "Get-NetAdapter" in args[-1]:
        if state.get("vpn_probe_rc"):
            return int(state["vpn_probe_rc"])
        print(json.dumps(state.get("vpns", [])))
        return 0
    if state.get("task_state_rc"):
        print("Get-ScheduledTask : Access is denied.", file=sys.stderr)
        return int(state["task_state_rc"])
    name = re.search(r"-eq '([^']+)'", args[-1]).group(1)
    tasks = state.get("tasks", {})
    print((4 if tasks[name] == "Running" else 3) if name in tasks else "absent")
    if name in tasks:  # then its action: the program and the working directory, one line each
        for tag in ("Command", "WorkingDirectory"):
            found = re.search(f"<{tag}>([^<]*)</{tag}>", state.get("task_xml", ""))
            print(found.group(1) if found else "")
    return 0


def schtasks(args, state):
    tasks = state.setdefault("tasks", {})
    name = args[args.index("/TN") + 1]
    verb = args[0]
    if verb != "/Create" and name not in tasks:
        print("ERROR: The system cannot find the file specified.", file=sys.stderr)
        return 1
    if verb == "/Query":
        # What a German Windows prints: a deploy that reads the state from this text gets it wrong
        word = "Wird ausgeführt" if tasks[name] == "Running" else "Bereit"
        print(f"Aufgabenname:  \\{name}\nStatus:        {word}")
        return 0
    if verb == "/Create":
        xml = Path(args[args.index("/XML") + 1]).read_text(encoding="utf-16")
        state["task_xml"] = xml
        tasks[name] = "Ready"
    elif verb == "/Run":
        tasks[name] = "Running"
    elif verb == "/End":
        if state.get("end_rc"):
            print("ERROR: Access is denied.", file=sys.stderr)
            return int(state["end_rc"])
        if not state.get("end_noop"):
            tasks[name] = "Ready"
    elif verb == "/Delete":
        del tasks[name]
    save(state)
    return 0


def netsh(args, state):
    rules = state.setdefault("rules", {})
    opts = dict(a.split("=", 1) for a in args if "=" in a)
    name = opts.get("name", "")
    verb = args[2]
    if verb in ("show", "delete") and name not in rules:
        print("\nNo rules match the specified criteria.\n")
        return 1
    ports = state.setdefault("rule_ports", {})
    if verb == "show":
        print(f"Rule Name:    {name}\nEnabled:      Yes\nRemoteIP:     {rules[name]}\n"
              f"LocalPort:    {ports.get(name, '')}\nOk.")
        return 0
    if verb == "add":
        rules[name], ports[name] = opts["remoteip"], opts["localport"]
    else:
        del rules[name]
        ports.pop(name, None)
    save(state)
    print("Ok.")
    return 0


def claude(args, state):
    plugins, mcp = state.setdefault("plugins", []), state.setdefault("mcp", {})
    if args[:2] == ["plugin", "list"]:
        print("Installed plugins:\n" + "".join(f"\n  > {p}\n    Status: enabled\n" for p in plugins))
        return 0
    if args[:2] == ["plugin", "install"]:
        plugins.append(args[2])
    elif args[:2] == ["plugin", "uninstall"]:
        plugins.remove(args[2])
    elif args[:2] == ["mcp", "get"]:
        if args[2] not in mcp:
            print(f'No MCP server named "{args[2]}".', file=sys.stderr)
            return 1
        print(f"{args[2]}:\n  Command: {mcp[args[2]][0]}\n  Args: {' '.join(mcp[args[2]][1:])}")
        return 0
    elif args[:2] == ["mcp", "add"]:
        mcp[args[4]] = args[args.index("--") + 1:]
    elif args[:2] == ["mcp", "remove"]:
        if args[-1] not in mcp:
            print(f'No MCP server named "{args[-1]}" found', file=sys.stderr)
            return 1
        del mcp[args[-1]]
    else:
        return 64
    save(state)
    return 0


TOOLS = {f.__name__: f for f in (tailscale, sudo, tee, rm, systemctl, ufw, schtasks, netsh, claude,
                                 curl, sh, winget, msiexec, brew, install)}
TOOLS["apt-get"] = apt_get
TOOLS["firewall-cmd"] = firewall_cmd
TOOLS["powershell"] = powershell
TOOLS["ip"] = ip


def main() -> int:
    name, args = sys.argv[1], sys.argv[2:]
    with open(os.environ["FAKE_DEPLOY_LOG"], "a", encoding="utf-8") as fh:
        fh.write(json.dumps([name, *args]) + "\n")
    return TOOLS[name](args, load())


if __name__ == "__main__":
    sys.exit(main())
