"""Stand-in for every system tool deploy.py drives: one program, the tool's name as argv[1].

tailscale, sudo, tee, rm, systemctl, ufw, schtasks, netsh, claude, and the Tailscale
installers curl, sh, install, apt-get, winget, msiexec and brew. State is the
JSON file in $FAKE_DEPLOY_STATE; every call's argv is appended to $FAKE_DEPLOY_LOG,
one JSON list per line. Nothing outside those two files and the paths a test
hands it is ever touched.

State keys: ts_ip, ts_backend, units {name: {active, enabled}}, ufw [lines],
tasks {name: status}, rules {name: remoteip}, plugins [ids], mcp {name: argv},
rule_ports {name: localport}, disable_rc (exit code of systemctl disable),
ts_node_id, install_rc (exit code of an installer), shim (the launcher text an
installer writes as the tailscale command into $FAKE_DEPLOY_BIN).
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def load() -> dict:
    return json.loads(Path(os.environ["FAKE_DEPLOY_STATE"]).read_text(encoding="utf-8"))


def save(state: dict) -> None:
    text = json.dumps(state)  # build the payload before the write truncates the file
    Path(os.environ["FAKE_DEPLOY_STATE"]).write_text(text, encoding="utf-8")


def tailscale(args, state):
    if args[:2] == ["ip", "-4"]:
        if not state.get("ts_ip"):
            print("no current Tailscale IPs; state: Stopped", file=sys.stderr)
            return 1
        print(state["ts_ip"])
        return 0
    if args and args[0] == "status":
        print(json.dumps({"BackendState": state.get("ts_backend", "Running"),
                          "Self": {"ID": state.get("ts_node_id", "nFAKENODE11CNTRL")}}))
        return 0
    if args and args[0] == "up":
        state["ts_backend"] = "Running"
        state["ts_ip"] = state.get("ts_ip") or "127.0.0.1"
        save(state)
        return 0
    return 64


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
    return 0


def curl(args, state):
    # curl_404: a part of the URL the server does not have (curl -f exits 22)
    if state.get("curl_404") and any(state["curl_404"] in arg for arg in args):
        print("curl: (22) The requested URL returned error: 404", file=sys.stderr)
        return 22
    Path(args[args.index("-o") + 1]).write_text("# fake download\n", encoding="utf-8")
    return 0


def install(_args, _state):
    return 0  # the real one would copy a file into /usr/share or /etc: never here


def apt_get(args, state):
    if args[:1] == ["update"]:
        return 0
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
        print("Status: active\n\nTo                         Action      From")
        print("--                         ------      ----")
        print("\n".join(rules))
        return 0
    delete = args[0] == "delete"
    words = args[1:] if delete else args
    subnet, port = words[words.index("from") + 1], words[words.index("port") + 1]
    line = f"{port}/tcp                   ALLOW       {subnet}"
    if delete:
        rules.remove(line)
    else:
        rules.append(line)
    save(state)
    return 0


def schtasks(args, state):
    tasks = state.setdefault("tasks", {})
    name = args[args.index("/TN") + 1]
    verb = args[0]
    if verb != "/Create" and name not in tasks:
        print("ERROR: The system cannot find the file specified.", file=sys.stderr)
        return 1
    if verb == "/Query":
        print(f"TaskName:      \\{name}\nStatus:        {tasks[name]}")
        return 0
    if verb == "/Create":
        xml = Path(args[args.index("/XML") + 1]).read_text(encoding="utf-16")
        state["task_xml"] = xml
        tasks[name] = "Ready"
    elif verb == "/Run":
        tasks[name] = "Running"
    elif verb == "/End":
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


def main() -> int:
    name, args = sys.argv[1], sys.argv[2:]
    with open(os.environ["FAKE_DEPLOY_LOG"], "a", encoding="utf-8") as fh:
        fh.write(json.dumps([name, *args]) + "\n")
    return TOOLS[name](args, load())


if __name__ == "__main__":
    sys.exit(main())
