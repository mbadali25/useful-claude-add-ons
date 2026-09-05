#!/usr/bin/env python3
"""Action layer for the Obsidian Local REST API bridge: scan, diagnose, repair.

bridge_status.py reports at session start and never touches anything. This is
the half that can act - and every subcommand that can act is dry-run by
default, printing the exact change it would make. `--apply` is the only thing
that writes.

    scan            [--json]                          every vault: ports, plugin, registration
    diagnose        [--vault NAME] [--json]           health verdict, collisions named first
    profile         [--vault NAME] [--json] [--set]   which plugin profile this vault is, and why
    fix-ports       [--vault NAME] [--apply]          assign non-colliding ports, write data.json
    reload          [--vault NAME | --all]            app:reload so a data.json edit takes effect
    register        [--vault NAME | --all] [--apply]  claude mcp add/remove per vault
    enable-plugin   [--vault NAME | --all] [--apply]  enable already-downloaded profile plugins
    add-vault       --name N --path P [--apply]       name a vault so --vault N resolves
    graph-health    [--vault NAME] [--fix]            codegraph vault layout and staleness

Exit codes: 0 healthy or applied, 1 problems found, 2 usage or structural error.

Three rules this file exists to enforce, each learned from a fault that shipped:

* **Never derive one port from the other.** data.json's "port" is HTTPS and
  "insecurePort" is HTTP; they are independent numbers, and on the machine this
  was written for one vault runs HTTPS 27126 / HTTP 27127 - below, not above.
  Both are read, or neither is reported.
* **Probe with curl -k on the HTTPS side.** Claude Code's Node MCP client
  rejects the self-signed certificate, and so does urllib; curl with -k does
  not. An HTTPS check that silently fails on the certificate looks exactly like
  a vault that is down.
* **Ask who answered, not just whether something did.** A server that is up,
  authenticated and serving a *different* vault passes every liveness check
  ever written for this plugin. That is how two vaults sharing port 27126 stayed
  undiagnosed: the loser's plugin never started, the winner answered on the
  loser's port with the winner's key and the winner's files, and the reported
  diagnosis was a flag that was already set correctly. Identity gets its own
  verdict here.

And one that governs every write: the Local REST API plugin reads data.json
**only at load**. After a write, the live instance disagrees with disk on both
the port and the API key, so nothing that writes data.json may claim the change
took effect - it says what still has to be reloaded, and `reload` is issued
against the port and key that were live *before* the write, since that is where
the running server still is.

The same rule, one layer out, governs `enable-plugin`: enabling a plugin edits
`community-plugins.json`, which Obsidian reads only at LAUNCH - a reload is not
enough there - and no plugin is ever enabled under a blanket yes. Each one is
named explicitly with `--plugin ID`, because a plugin is load-bearing for
whatever renders through it and a batched "install these thirteen" is the same
mistake as a batched removal. What the profile wants is reported; what gets
written is what was asked for by name.
"""
import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import obsidian_common  # noqa: E402  pylint: disable=wrong-import-position
import vault_profiles  # noqa: E402  pylint: disable=wrong-import-position

EXIT_OK = 0
EXIT_PROBLEMS = 1
EXIT_USAGE = 2

# One definition, in vault_profiles, where the install side and the strip side
# both read it. The name stays here because every caller and test in this file
# already uses it.
REST_PLUGIN_ID = vault_profiles.BRIDGE_PLUGIN_ID
RELOAD_COMMAND = "app:reload"
STALE_DAYS = 30


# --- Probing -----------------------------------------------------------------

class Prober:
    """Everything that touches the network, in one place so tests can replace it.

    `get` returns (data, error): data is the parsed JSON body on success and
    error is a short human string on failure. Errors are values rather than
    exceptions because every caller here treats "did not answer" as one more
    verdict to report, not as a reason to stop.
    """

    def __init__(self, timeout=3.0):
        self.timeout = timeout

    def listening(self, port):
        if not port:
            return False
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.4):
                return True
        except OSError:
            return False

    def get(self, protocol, port, api_key, path="/"):
        return self.request(protocol, port, api_key, path, method="GET")

    def request(self, protocol, port, api_key, path="/", method="GET"):
        if not port:
            return None, "no port"
        if protocol == "https":
            return self._curl(port, api_key, path, method)
        return self._urllib(port, api_key, path, method)

    def _urllib(self, port, api_key, path, method):
        import urllib.error
        import urllib.request
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}{path}",
            headers={"Authorization": f"Bearer {api_key or ''}"},
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return _decode(r.read()), None
        except urllib.error.HTTPError as e:
            body = _decode(e.read())
            if isinstance(body, dict):
                return body, f"HTTP {e.code}"
            return None, f"HTTP {e.code}"
        except Exception as e:  # pylint: disable=broad-except
            return None, type(e).__name__

    def _curl(self, port, api_key, path, method):
        # curl, not urllib: the HTTPS listener presents a self-signed
        # certificate, which urllib (and Claude Code's own Node MCP client)
        # rejects outright. -k is the whole reason this branch exists; without
        # it a perfectly healthy HTTPS bridge reports as unreachable.
        curl = shutil.which("curl")
        if not curl:
            return None, "curl not found (needed for the self-signed HTTPS port)"
        cmd = [curl, "-k", "-sS", "--max-time", str(int(self.timeout)),
               "-X", method,
               "-H", f"Authorization: Bearer {api_key or ''}",
               "-w", "\n%{http_code}", f"https://127.0.0.1:{port}{path}"]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=self.timeout + 2, check=False)
        except (OSError, subprocess.SubprocessError) as e:
            return None, type(e).__name__
        if proc.returncode != 0:
            return None, (proc.stderr or "").strip() or f"curl exit {proc.returncode}"
        body, _, code = proc.stdout.rpartition("\n")
        data = _decode(body)
        if code.strip() and not code.strip().startswith("2"):
            return data, f"HTTP {code.strip()}"
        return data, None


def _decode(raw):
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "replace")
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


def authenticated(data):
    return isinstance(data, dict) and data.get("authenticated") is True


# --- Registration (claude mcp) -----------------------------------------------

def mcp_servers():
    """{name: url} from `claude mcp list`, or None when the CLI cannot answer.

    None is deliberately distinct from {}: "no servers registered" and "we
    could not find out" lead to opposite advice, and collapsing them is how a
    tool ends up telling someone to re-add a server they already have.
    """
    claude = shutil.which("claude")
    if not claude:
        return None
    try:
        proc = subprocess.run([claude, "mcp", "list"], capture_output=True, text=True,
                              timeout=60, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0 and not proc.stdout:
        return None
    out = {}
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        name, _, rest = line.partition(":")
        name = name.strip()
        if not name or " " in name:
            continue
        url = rest.strip().split(" ")[0]
        out[name] = url
    return out


def mcp_server_key(name):
    """The Bearer token `claude mcp get <name>` reports, or None if unreadable.

    `claude mcp list` prints only name and URL, so URL equality says nothing
    about whether the stored key still matches the vault's. `mcp mcp get` does
    print the header, which is the difference between "already registered" as a
    fact and as a guess. None means could-not-read, and callers must treat that
    as unknown rather than as a match - a rotated key that reports itself
    current is a bridge that never authenticates again.
    """
    claude = shutil.which("claude")
    if not claude:
        return None
    try:
        proc = subprocess.run([claude, "mcp", "get", name], capture_output=True,
                              text=True, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return parse_mcp_get_key(proc.stdout)


# Values a CLI might print INSTEAD of the key. None of these is a key, and
# treating one as a key would classify every correct registration as rotated and
# rewrite it on every run - silently and destructively, because nothing about
# that looks wrong from the outside.
#
# As of 2026-09-05 this machine's `claude mcp get` prints the token verbatim, so
# none of these is currently produced. This is insurance against a format change,
# not a workaround for one: do not delete it as dead code, and do not read it as
# evidence that redaction is happening.
_REDACTION_MARKERS = ("[redacted]", "<redacted>", "redacted", "***", "********",
                      "[hidden]", "<hidden>")


def parse_mcp_get_key(stdout):
    """The Bearer token in `claude mcp get` output, or None if there is not one.

    Split out from the subprocess call so the parsing is testable against real
    captured output. None means "no key here" and callers must treat it as
    unknown rather than as a mismatch.
    """
    for line in (stdout or "").splitlines():
        line = line.strip()
        if not line.lower().startswith("authorization:"):
            continue
        _, _, value = line.partition(":")
        value = value.strip()
        if value.lower() == "bearer":
            return None
        if value.lower().startswith("bearer "):
            value = value[len("bearer "):].strip()
        if not value:
            return None
        stripped = value.strip("*")
        if value.lower() in _REDACTION_MARKERS or (not stripped and value):
            return None
        return value
    return None


def run_command(cmd):
    """Execute one `claude mcp ...` command. (returncode, ok).

    The single execution boundary for this file, so a test can replace it and
    assert that nothing ran. Inline subprocess calls cannot be observed that
    way, which is how an assertion that "no commands were executed" ends up
    proving nothing.
    """
    claude = shutil.which("claude")
    if not claude:
        return 127, False
    try:
        proc = subprocess.run([claude] + cmd[1:], capture_output=True, text=True,
                              timeout=120, check=False)
    except (OSError, subprocess.SubprocessError) as e:
        print(f"{type(e).__name__} running the claude CLI", file=sys.stderr)
        return 1, False
    if proc.returncode != 0:
        # Reported here rather than by the caller: the caller does not hold the
        # process, and a failing CLI call whose stderr is dropped is a failure
        # nobody can act on.
        print((proc.stderr or proc.stdout or "").strip(), file=sys.stderr)
    return proc.returncode, proc.returncode == 0


def server_name(vault_name):
    return f"obsidian-{vault_name}"


def server_url(http_port):
    return f"http://127.0.0.1:{http_port}/mcp"


def find_registration(registered, vault_name, http_port):
    """(server name, url) already registered for this vault, or (None, None).

    Matched by URL as well as by name. The first vault anyone sets up is
    commonly registered as plain `obsidian` rather than `obsidian-<name>` -
    that is the case on the machine this was written for - and a name-only
    lookup calls it unregistered and then proposes adding a second server
    pointing at the same port.
    """
    if not registered:
        return None, None
    canonical = server_name(vault_name)
    if canonical in registered:
        return canonical, registered[canonical]
    if http_port:
        target = server_url(http_port)
        for name, url in registered.items():
            if url == target and name.startswith("obsidian"):
                return name, url
    return None, None


# --- Vault enumeration -------------------------------------------------------

def enumerate_vaults():
    """(vaults, settings) for every vault on the machine, configured or not."""
    vaults = obsidian_common.discover_vaults()
    return vaults, obsidian_common.collect_rest_settings(vaults)


def configured_names():
    """Vault names the user actually put in config, including the legacy shape."""
    config = obsidian_common.read_config()
    vaults = config.get("vaults")
    if isinstance(vaults, dict) and vaults:
        return set(vaults)
    return {"memory"} if config.get("vaultPath") else set()


def unconfigured(vaults):
    """Discovered-but-unconfigured names, so a caller can say what it skipped."""
    return sorted(set(vaults) - configured_names())


def missing_configured(vaults):
    """Configured vaults discovery could not find, with why, for --all callers.

    A vault in config but not in discovery is one whose directory is gone, was
    renamed, or lives on a drive that is not mounted. Filtering `--all` down to
    the configured set turns that into an empty selection, and an empty
    selection that exits 0 reports success for work nobody did - the exact
    failure this file's exit codes exist to prevent. Named and counted instead.
    """
    out = []
    config = obsidian_common.read_config()
    declared = config.get("vaults")
    declared = declared if isinstance(declared, dict) else {}
    for name in sorted(configured_names() - set(vaults)):
        entry = declared.get(name) or {}
        # Decide from whether a path was actually FOUND. Deciding from the
        # display string makes the no-path branch unreachable, because the
        # placeholder is itself truthy - and a vault configured as {} then gets
        # reported as one whose directory was deleted.
        found = entry.get("path") or config.get("vaultPath")
        path = found or "<no path in config>"
        if not found:
            why = "no path recorded in config for this vault"
        elif not os.path.exists(found):
            why = "path does not exist - deleted, renamed, or on a drive that is not mounted"
        else:
            why = "path exists but Obsidian does not know this vault"
        out.append((name, path, why))
    return out


def select(vaults, name=None, all_vaults=False, require_choice=False):
    """The subset a subcommand should act on, or (None, message) on a usage error.

    `--all` means every CONFIGURED vault, never every vault on the machine.
    enumerate_vaults() deliberately discovers vaults config has never heard of,
    because a bridge that ignores them cannot diagnose a port collision they
    are causing. Acting on them is a different matter entirely: `register --all`
    would write a user-scope MCP server for someone's private journal, and
    `enable-plugin --all` would edit its community-plugins.json. Naming a vault
    with --vault is consent; being on the same disk is not.
    """
    if name and all_vaults:
        return None, "--vault and --all are mutually exclusive"
    if name:
        if name not in vaults:
            known = ", ".join(sorted(vaults)) or "none found"
            return None, f"unknown vault {name!r} (known: {known})"
        return {name: vaults[name]}, None
    if require_choice and not all_vaults:
        return None, "one of --vault NAME or --all is required"
    if all_vaults:
        known = configured_names()
        return {n: v for n, v in vaults.items() if n in known}, None
    return dict(vaults), None


def ports_of(name, vaults, settings):
    entry = vaults[name]
    return obsidian_common.resolve_ports(entry["path"], entry.get("port"), settings.get(name))


# --- Diagnosis ---------------------------------------------------------------

def verdict(level, code, message):
    return {"level": level, "code": code, "message": message}


def _identity_verdicts(name, vaults, settings, http_port, https_port, prober):
    """Who is actually answering on this vault's ports.

    Two independent checks, because each catches a case the other misses:
    key ownership (a sibling vault's key authenticating here names the impostor
    outright) and the root listing compared against the directory on disk.

    Every listening port produces a verdict - confirmed, mismatched, or
    unknown. A check that says nothing when it succeeds is indistinguishable
    from a check that never ran, and "nothing noticed the wrong server" is the
    exact failure being fixed here: a `curl` that is missing, an HTTPS
    handshake that fails, or an empty root listing would otherwise read as
    silent approval.
    """
    out = []
    keys = {n: s["api_key"] for n, s in settings.items()
            if n != name and s.get("api_key")}
    paths = {n: e["path"] for n, e in vaults.items() if n != name}
    for protocol, port in (("http", http_port), ("https", https_port)):
        if not port or not prober.listening(port):
            continue
        proto = protocol.upper()
        mine_key = settings[name]["api_key"]
        data, err = prober.get(protocol, port, mine_key)
        if authenticated(data):
            listing, listing_err = prober.get(protocol, port, mine_key, "/vault/")
            files = listing.get("files") if isinstance(listing, dict) else None
            check = obsidian_common.identity_check(vaults[name]["path"], files, paths)
            if check["verdict"] == "mismatch":
                out.append(verdict(
                    "FAIL", "identity-mismatch",
                    f"{proto} :{port} authenticates but is serving the WRONG vault: "
                    f"{check['detail']}. Every read and write through this bridge would "
                    "hit the other vault."))
            elif check["verdict"] == "match":
                out.append(verdict(
                    "OK", "identity-confirmed",
                    f"{proto} :{port} is serving this vault's own files "
                    f"({check['detail']})."))
            else:
                out.append(verdict(
                    "WARN", "identity-unknown",
                    f"{proto} :{port} answers, but which vault it serves could not be "
                    f"confirmed: {check['detail']}"
                    + (f" (/vault/ said: {listing_err})" if listing_err else "") + "."))
            continue
        if data is None:
            # No answer at all: a transport failure, not a rejection. On the
            # HTTPS side this is usually a missing curl or a handshake the
            # client refused - which must not read as "identity fine".
            out.append(verdict(
                "WARN", "identity-unknown",
                f"{proto} :{port} is open but did not answer ({err}), so which vault owns "
                "that port is unknown."))
            continue
        # Our own key was refused. Before blaming the key, find out whose
        # server this is - that is the check whose absence hid the original
        # fault for weeks.
        impostor = None
        for other, key in keys.items():
            other_data, _ = prober.get(protocol, port, key)
            if authenticated(other_data):
                impostor = other
                break
        if impostor:
            out.append(verdict(
                "FAIL", "identity-mismatch",
                f"{proto} :{port} rejects this vault's key but ACCEPTS vault "
                f"'{impostor}'s key - the server on that port belongs to '{impostor}', "
                f"not to '{name}'."))
        else:
            out.append(verdict(
                "WARN", "identity-unknown",
                f"{proto} :{port} rejected this vault's key, and no other known vault's "
                "key was accepted either, so who owns that port is unknown."))
    return out


def diagnose_vault(name, vaults, settings, collisions, prober):
    """The full verdict list for one vault, collisions first."""
    entry = vaults[name]
    s = settings[name]
    http_port, https_port = ports_of(name, vaults, settings)
    result = {
        "vault": name,
        "path": entry["path"],
        "http_port": http_port,
        "https_port": https_port,
        "plugin_installed": s["installed"],
        "enable_insecure_server": s["enable_insecure_server"],
        "source": entry.get("source", "config"),
        "verdicts": [],
    }
    mine = obsidian_common.collisions_for(collisions, name)

    # Collisions are stated before anything else is even probed. A duplicate
    # port takes the losing vault down on BOTH protocols at once, and each of
    # the symptoms that produces has a convincing wrong explanation of its own.
    for c in mine:
        others = sorted({claim["vault"] for claim in c["claims"]} - {name})
        who = " and ".join(others) or "itself"
        result["verdicts"].append(verdict(
            "FAIL", "port-collision",
            f"{obsidian_common.describe_collision(c)}. Only one process can bind "
            f":{c['port']}; the loser's Local REST API plugin fails to start its server "
            f"at all, so it serves NOTHING on either protocol while {who} answers on that "
            f"port with {who}'s key and {who}'s files. Fix: vault_ops.py fix-ports "
            f"--vault {name}, then reload both vaults."))

    for w in s["warnings"]:
        result["verdicts"].append(verdict("WARN", "data-json", w))

    if not s["installed"]:
        where = ("the plugin folder exists but has never run"
                 if s["plugin_dir_present"] else "no plugin folder either")
        result["verdicts"].append(verdict(
            "FAIL", "plugin-not-installed",
            f"Local REST API is not installed for this vault - no {s['data_path']} "
            f"({where}). This is not a bridge that is down; there is no bridge. "
            f"Fix: vault_ops.py install-plugin --vault {name}."))
        result["healthy"] = False
        return result

    if http_port is None and https_port is None:
        result["verdicts"].append(verdict(
            "FAIL", "no-ports",
            f"{s['data_path']} names no usable port ('insecurePort' for HTTP, 'port' for "
            "HTTPS). Nothing can be probed."))
        result["healthy"] = False
        return result

    http_up = prober.listening(http_port)
    https_up = prober.listening(https_port)
    result["http_listening"] = http_up
    result["https_listening"] = https_up

    if not http_up and not https_up:
        if not mine:
            result["verdicts"].append(verdict(
                "FAIL", "down",
                f"Nothing listening on 127.0.0.1:{http_port} (HTTP) or :{https_port} "
                "(HTTPS). Obsidian is not running this vault, or was launched before the "
                "plugin was enabled - it needs a full quit from the tray icon, then a "
                "relaunch."))
        result["healthy"] = False
        return result

    if not http_up:
        if mine:
            pass  # already diagnosed above; the flag is not the cause
        elif s["enable_insecure_server"] is False:
            result["verdicts"].append(verdict(
                "FAIL", "insecure-server-disabled",
                f"HTTPS :{https_port} is up but HTTP :{http_port} is down, and "
                f"'enableInsecureServer' is false in {s['data_path']}. Set it to true and "
                f"reload ({RELOAD_COMMAND}). Do not repoint the MCP server at "
                f":{https_port} - Claude Code's Node client rejects the self-signed "
                "certificate."))
        else:
            result["verdicts"].append(verdict(
                "FAIL", "http-down",
                f"HTTPS :{https_port} is up but HTTP :{http_port} is down while "
                f"'enableInsecureServer' is already true in {s['data_path']} - that flag "
                f"is NOT the cause, do not re-tick it. The running plugin read data.json "
                f"at load and has not seen it since: reload ({RELOAD_COMMAND}) so the live "
                "instance matches disk."))

    if http_up:
        data, err = prober.get("http", http_port, s["api_key"])
        if data is None:
            result["verdicts"].append(verdict(
                "FAIL", "api-silent",
                f"Port :{http_port} is open but the API did not answer ({err})."))
        elif not authenticated(data):
            result["verdicts"].append(verdict(
                "FAIL", "auth-rejected",
                f"Reachable on :{http_port} but the API key from {s['data_path']} was "
                "REJECTED."))
        else:
            ver = data.get("versions") or {}
            result["versions"] = ver
            result["verdicts"].append(verdict(
                "OK", "up",
                f"HTTP :{http_port} up and authenticated (Obsidian "
                f"{ver.get('obsidian', '?')}, Local REST API {ver.get('self', '?')})."))

    result["verdicts"].extend(
        _identity_verdicts(name, vaults, settings, http_port, https_port, prober))
    result["healthy"] = not any(v["level"] == "FAIL" for v in result["verdicts"])
    return result


def print_verdicts(result):
    print(f"{result['vault']}  ({result['path']})")
    print(f"  ports: HTTP {result['http_port'] or '-'}  HTTPS {result['https_port'] or '-'}"
          f"   plugin: {'installed' if result['plugin_installed'] else 'NOT INSTALLED'}")
    for v in result["verdicts"]:
        print(f"  [{v['level']}] {v['message']}")
    if not result["verdicts"]:
        print("  [OK] nothing to report")


# --- scan --------------------------------------------------------------------

def cmd_scan(args, prober):
    vaults, settings = enumerate_vaults()
    collisions = obsidian_common.find_port_collisions(vaults, settings)
    registered = mcp_servers()
    rows = []
    for name in sorted(vaults):
        entry = vaults[name]
        http_port, https_port = ports_of(name, vaults, settings)
        found, url = find_registration(registered, name, http_port)
        rows.append({
            "vault": name,
            "path": entry["path"],
            "http_port": http_port,
            "https_port": https_port,
            "plugin_installed": settings[name]["installed"],
            "enable_insecure_server": settings[name]["enable_insecure_server"],
            "registered": None if registered is None else found is not None,
            "mcp_server": found,
            "mcp_url": url,
            "source": entry.get("source", "config"),
            "default": entry.get("default", False),
        })
    if args.json:
        print(json.dumps({"vaults": rows,
                          "collisions": collisions,
                          "registration_known": registered is not None}, indent=2))
    else:
        print(f"{len(rows)} vault(s) found (configured + Obsidian's own registry)\n")
        for r in rows:
            reg = "?" if r["registered"] is None else ("yes" if r["registered"] else "no")
            plugin = "yes" if r["plugin_installed"] else "NO REST API plugin"
            print(f"{r['vault']}{' (default)' if r['default'] else ''}")
            print(f"  path       {r['path']}  [{r['source']}]")
            print(f"  http       {r['http_port'] or '-'}    https {r['https_port'] or '-'}")
            print(f"  plugin     {plugin}")
            print(f"  mcp server {reg}"
                  + (f"  {r['mcp_server']} -> {r['mcp_url']}" if r["mcp_url"] else ""))
        if registered is None:
            print("\nRegistration is unknown: the `claude` CLI is not on PATH here.")
        for c in collisions:
            print(f"\n[FAIL] {obsidian_common.describe_collision(c)} - the vault that loses "
                  "the bind serves nothing on either protocol.")
    return EXIT_PROBLEMS if collisions else EXIT_OK


# --- diagnose ----------------------------------------------------------------

def cmd_diagnose(args, prober):
    vaults, settings = enumerate_vaults()
    chosen, err = select(vaults, args.vault)
    if err:
        print(err, file=sys.stderr)
        return EXIT_USAGE
    if not vaults:
        print("No vaults found (nothing configured, and Obsidian's registry is empty).")
        return EXIT_PROBLEMS
    collisions = obsidian_common.find_port_collisions(vaults, settings)
    results = [diagnose_vault(name, vaults, settings, collisions, prober)
               for name in sorted(chosen)]

    # Every collision on the machine is printed - a collision the selected vault
    # is not part of is exactly what a wide diagnosis is for, and hiding it to
    # make the exit code true would delete the most useful line on the screen.
    # But only a collision INVOLVING the selection is a failure of what was
    # asked, so the label carries the scope and the exit code stays scoped.
    # Folding every collision into the exit code would tell a user who asked
    # about one vault that their question failed because two others clash.
    #
    # With no --vault, chosen is every vault, so every collision is in scope and
    # this is byte-identical to the unscoped behaviour it replaces.
    for c in collisions:
        c["in_scope"] = any(claim["vault"] in chosen for claim in c["claims"])
    if args.json:
        print(json.dumps({"collisions": collisions, "vaults": results}, indent=2))
    else:
        for c in collisions:
            if c["in_scope"]:
                print(f"[FAIL] {obsidian_common.describe_collision(c)}")
            else:
                who = ", ".join(sorted({claim["vault"] for claim in c["claims"]}))
                print(f"[ELSEWHERE] {obsidian_common.describe_collision(c)} - not a "
                      f"failure of what you asked about; it is {who}'s. Diagnose or fix "
                      f"those with --vault, or run unscoped.")
        if collisions:
            print()
        for r in results:
            print_verdicts(r)
            print()
    return EXIT_OK if all(r["healthy"] for r in results) else EXIT_PROBLEMS


# --- fix-ports ---------------------------------------------------------------

def claimed_ports(vaults, settings):
    ports = set()
    for s in settings.values():
        for p in (s["https_port"], s["http_port"]):
            if p:
                ports.add(p)
    return ports


def next_free_port(taken, start, prober=None):
    """The first port at or above `start` nobody claims and nothing is bound to.

    Both conditions matter: a port no vault has declared can still be in use by
    something else entirely, and moving a vault onto it just relocates the
    outage.
    """
    port = max(1024, int(start))
    while port <= 65535:
        if port not in taken and not (prober and prober.listening(port)):
            return port
        port += 1
    return None


def unconfigured_step(name, key, port):
    """A collision whose mover is a vault the user never put under this plugin.

    fix-ports edits a vault's OWN data.json, which is a heavier write than the
    MCP config `--all` was fenced off from - so the same consent rule applies,
    and this is the site that does not go through select(). Refused rather than
    worked around: silently moving the other vault instead would hide a real
    conflict and move a vault that was not at fault. The user is told exactly
    which vault has to opt in before the collision can be fixed.
    """
    return {
        "vault": name, "key": key, "from": port, "to": None, "blocked": True,
        "why": (f"{name} is not in your config, and fix-ports writes a vault's own "
                f"data.json. Opt it in first: vault_ops.py add-vault --name {name} "
                f"--path <path> --apply, then re-run. Nothing else here can end this "
                f"collision on :{port} without moving a vault you never named."),
    }


def unnamed_mover_step(name, key, port, only):
    """A collision whose fix needs a vault other than the one --vault named.

    Scoping to X and editing X's neighbour's data.json is the same shape as
    editing an unconfigured vault, one level up: being in config is consent to
    be managed by this plugin, not consent to be edited by a command aimed at
    something else. A scripted `fix-ports --vault memory --apply` in a hook
    never reads a plan first.

    Refused rather than silently skipped, because the collision is real and the
    diagnosis just named it. The unscoped run is what actually fixes it - the
    vault that keeps its port is still the one holding the bind.
    """
    return {
        "vault": name, "key": key, "from": port, "to": None, "blocked": True,
        "why": (f"ending this collision on :{port} means moving {name}, which you did "
                f"not name - you scoped this run to {only!r}. Re-run without --vault to "
                f"fix it, or name {name} explicitly if you want it moved."),
    }


def claimed_keys(collision, name):
    """The data.json keys `name` claims in this collision, HTTP before HTTPS.

    A vault can claim the same port on both protocols, so this is a set rather
    than a choice - picking one with an any() moves half the collision and
    leaves the other half in place.
    """
    return sorted({"port" if claim["protocol"] == "https" else "insecurePort"
                   for claim in collision["claims"] if claim["vault"] == name})


def blocked_step(name, key, port):
    """A collision with no replacement port available.

    Writing the None that next_free_port returned would put JSON null in
    data.json, replacing a port that at least one vault can bind with one
    nothing can - strictly worse than the collision it was fixing. The plan
    carries the refusal instead, so the user is told why rather than being
    handed a broken vault.
    """
    return {
        "vault": name, "key": key, "from": port, "to": None, "blocked": True,
        "why": (f"no free port is available above :{port}; every candidate up to 65535 "
                "is claimed by another vault or already listening"),
    }


def plan_port_fix(vaults, settings, collisions, prober, only=None, allowed=None):
    """What to change, and in which vault, to end every collision.

    The vault that keeps its port is the one currently answering on it - the
    winner of the bind. Moving the winner would break a bridge that works, and
    leave the loser still dark until Obsidian is restarted anyway. When neither
    side answers, the tie is broken by name so the plan is deterministic and
    the same on a second run.

    Only CONFIGURED vaults are moved. This command writes a vault's own
    data.json, which is a heavier write than the MCP config `--all` was already
    fenced off from, and it is the one acting command that never goes through
    select(). A collision whose mover is unconfigured is refused by name rather
    than worked around, so a real conflict stays visible.
    """
    # None means "read the config", which is what production wants. Callers
    # testing port arithmetic pass an explicit set so they do not depend on
    # whatever happens to be configured on the machine running them.
    allowed = configured_names() if allowed is None else set(allowed)
    taken = claimed_ports(vaults, settings)
    plan = []
    for c in collisions:
        names = sorted({claim["vault"] for claim in c["claims"]})
        # `only` scopes which COLLISIONS to act on, not which vault moves. A
        # user who scopes to the vault currently holding the port still wants
        # the collision fixed; filtering the movers instead would report
        # "nothing to do" for a collision the diagnosis just named.
        if only and only not in names:
            continue
        if len(names) < 2:
            # One vault claiming the same port for both protocols.
            name = names[0]
            if name not in allowed:
                for key in claimed_keys(c, name):
                    plan.append(unconfigured_step(name, key, c["port"]))
                continue
            new_port = next_free_port(taken, c["port"] + 1, prober)
            if new_port is None:
                plan.append(blocked_step(name, "port", c["port"]))
                continue
            taken.add(new_port)
            plan.append({"vault": name, "key": "port", "from": c["port"], "to": new_port,
                         "why": f"{name} uses :{c['port']} for both HTTP and HTTPS"})
            continue
        holder = None
        for n in names:
            if prober.listening(c["port"]):
                data, _ = prober.get("http", c["port"], settings[n]["api_key"])
                if not authenticated(data):
                    data, _ = prober.get("https", c["port"], settings[n]["api_key"])
                if authenticated(data):
                    holder = n
                    break
        movers = [n for n in names if n != (holder or names[0])]
        for n in movers:
            if n not in allowed:
                for key in claimed_keys(c, n):
                    plan.append(unconfigured_step(n, key, c["port"]))
                continue
            if only and n != only:
                for key in claimed_keys(c, n):
                    plan.append(unnamed_mover_step(n, key, c["port"], only))
                continue
            # A mover can claim the same port on BOTH protocols - the shape the
            # single-vault branch above already handles. Picking one key with an
            # any() moves half of it and leaves the other half colliding, while
            # --apply reports success. Emit a step per protocol this vault
            # actually claims.
            for key in claimed_keys(c, n):
                new_port = next_free_port(taken, c["port"] + 1, prober)
                if new_port is None:
                    plan.append(blocked_step(n, key, c["port"]))
                    continue
                taken.add(new_port)
                plan.append({
                    "vault": n, "key": key, "from": c["port"], "to": new_port,
                    "why": (f"{holder} currently holds :{c['port']}" if holder
                            else f"neither vault answers on :{c['port']}; "
                                 f"moving {n} by name order"),
                })
    return plan


def write_data_json(path, changes):
    """Apply {key: value} to a data.json, preserving every other setting."""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    data.update(changes)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return data


def cmd_fix_ports(args, prober):
    vaults, settings = enumerate_vaults()
    if args.vault and args.vault not in vaults:
        print(f"unknown vault {args.vault!r}", file=sys.stderr)
        return EXIT_USAGE
    collisions = obsidian_common.find_port_collisions(vaults, settings)
    if not collisions:
        print("No port collisions: every vault's HTTP and HTTPS ports are unique.")
        return EXIT_OK
    plan = plan_port_fix(vaults, settings, collisions, prober, only=args.vault)
    if not plan:
        print("Collisions exist but none of them involve "
              f"{args.vault!r}; run without --vault to see the full plan.")
        return EXIT_PROBLEMS

    print("Planned changes (nothing is written without --apply):")
    for step in plan:
        s = settings[step["vault"]]
        label = "HTTPS" if step["key"] == "port" else "HTTP"
        if step.get("blocked"):
            print(f"  {step['vault']}: {label} {step['from']} -> REFUSED")
            print(f"    why:  {step['why']}")
            continue
        print(f"  {step['vault']}: {label} {step['from']} -> {step['to']}")
        print(f"    file: {s['data_path']}   key: \"{step['key']}\"")
        print(f"    why:  {step['why']}")
    if any(step.get("blocked") for step in plan):
        print("\nAt least one collision has no replacement port. Nothing is written: "
              "a partial fix would leave the plan half-applied and the diagnosis stale.")
        return EXIT_PROBLEMS
    if not args.apply:
        print("\nDry run. Re-run with --apply to write these changes.")
        return EXIT_PROBLEMS

    problems = False
    reloads = []
    for step in plan:
        s = settings[step["vault"]]
        # Captured BEFORE the write: the running plugin is still bound to the
        # old port and still holds the old key, so that is the only address a
        # reload can be delivered to. Re-reading data.json afterwards would dial
        # a port nothing is listening on and report a failure that is not one.
        live_http, live_https = obsidian_common.resolve_ports(
            vaults[step["vault"]]["path"], vaults[step["vault"]].get("port"), s)
        live_key = s["api_key"]
        try:
            write_data_json(s["data_path"], {step["key"]: step["to"]})
        except (OSError, ValueError) as e:
            print(f"  FAILED to write {s['data_path']}: {e}", file=sys.stderr)
            problems = True
            continue
        print(f"  wrote {s['data_path']}: {step['key']} = {step['to']}")
        if not args.reload:
            # A reload restarts a live Obsidian window under whoever is typing
            # in it. Approving an edit to a file on disk is not approving that,
            # and this script has no channel to ask - the command file does.
            # So say what is still outstanding and let the separately-confirmed
            # `reload` operation do it.
            reloads.append(step["vault"])
            continue
        ok, detail = reload_vault(step["vault"], live_http, live_https, live_key, prober)
        print(f"    reload via the pre-write port ({live_http or live_https}): {detail}")
        if not ok:
            problems = True
            print("    The write is on disk but NOT in effect: the plugin reads data.json "
                  "only at load, so the live server still has the old port and the old "
                  "key. Quit Obsidian from the tray icon and relaunch this vault.")
    if reloads:
        problems = True
        names = " ".join(sorted(set(reloads)))
        print("\nThe writes are on disk but NOT in effect. The plugin reads data.json only "
              "at load, so each live server still has its old port and old key. Reloading "
              "restarts a live window, so it is a separate yes:")
        for name in sorted(set(reloads)):
            print(f"  vault_ops.py reload --vault {name}")
        print(f"Until then, treat {names} as unchanged.")
    return EXIT_PROBLEMS if problems else EXIT_OK


# --- reload ------------------------------------------------------------------

def reload_vault(name, http_port, https_port, api_key, prober):
    """POST app:reload to whichever protocol answers. (ok, detail).

    Both protocols are tried before giving up. A vault can be reachable on
    HTTPS while HTTP rejects the request, and returning on the first refusal
    would report a remotely-reloadable vault as needing a manual restart.
    """
    refusals = []
    for protocol, port in (("http", http_port), ("https", https_port)):
        if not port or not prober.listening(port):
            continue
        _, err = prober.request(protocol, port, api_key,
                                f"/commands/{RELOAD_COMMAND}/", method="POST")
        if err is None:
            return True, f"{RELOAD_COMMAND} accepted on {protocol.upper()} :{port}"
        refusals.append(f"{protocol.upper()} :{port} refused it ({err})")
    if refusals:
        return False, "; ".join(refusals)
    return False, (f"nothing is listening on :{http_port or '-'} or :{https_port or '-'}, "
                   f"so {name} cannot be reloaded remotely - quit Obsidian from the tray "
                   "icon and relaunch this vault")


def cmd_reload(args, prober):
    vaults, settings = enumerate_vaults()
    chosen, err = select(vaults, args.vault, args.all, require_choice=True)
    if err:
        print(err, file=sys.stderr)
        return EXIT_USAGE
    all_problems = False
    if args.all:
        skipped = unconfigured(vaults)
        if skipped:
            print("Not touched by --all, because config has never named them: "
                  + ", ".join(skipped)
                  + ". Add one with `add-vault`, or act on it explicitly with --vault.")
        gone = missing_configured(vaults)
        for gone_name, gone_path, gone_why in gone:
            print(f"{gone_name}: configured, but not found - {gone_path}: {gone_why}. "
                  "Nothing here can act on it.", file=sys.stderr)
        if gone:
            # A configured vault that has vanished is a problem, not a clean
            # run. Exiting 0 here would report success for a vault the user
            # explicitly put under this plugin and that nothing touched.
            all_problems = True
        if not chosen:
            print("No configured vault could be acted on.", file=sys.stderr)
            return EXIT_PROBLEMS
    problems = all_problems
    for name in sorted(chosen):
        s = settings[name]
        http_port, https_port = ports_of(name, vaults, settings)
        ok, detail = reload_vault(name, http_port, https_port, s["api_key"], prober)
        print(f"{name}: {detail}")
        if not ok:
            problems = True
    print("\nA reload is what makes an edited data.json take effect - until it happens, "
          "the running plugin still has the port and API key it read at load.")
    return EXIT_PROBLEMS if problems else EXIT_OK


# --- register ----------------------------------------------------------------

def orphan_servers(registered, vaults, settings):
    """[(server, url)] for obsidian MCP servers pointing at no known vault.

    The case this catches: a vault registered under the legacy name `obsidian`
    has its port moved by fix-ports. find_registration then matches nothing (the
    name is not canonical and the URL is stale), so `register` proposes adding
    `obsidian-<name>` and the old entry is left behind, pointing at a dead port.
    Naming the leftover is as far as this goes - which of two servers a user's
    saved prompts already call is not something to guess at.
    """
    live = set()
    for name in vaults:
        http_port, _ = obsidian_common.resolve_ports(
            vaults[name]["path"], vaults[name].get("port"), settings.get(name))
        if http_port:
            live.add(server_url(http_port))
    return sorted((server, url) for server, url in (registered or {}).items()
                  if server.startswith("obsidian") and url not in live)


UNKNOWN_KEY = object()


def register_commands(name, http_port, api_key, found_name=None, existing_url=None,
                      existing_key=UNKNOWN_KEY):
    """The exact `claude mcp` invocations for this vault, or [] when correct.

    A server already pointing at this vault's URL is left alone even when it
    is registered under a legacy name - renaming it would break every
    mcp__<name>__* call in every saved prompt and skill that already uses it.

    The URL is only half the registration. A rotated apiKey leaves the URL
    identical and the bridge permanently unauthenticated, so a URL match is
    evidence about the URL and nothing else. `existing_key` closes that: the
    key read back from `claude mcp get`, or UNKNOWN_KEY when it could not be
    read. Unknown re-registers rather than assuming a match - re-registering a
    correct server costs one CLI call, and assuming a stale one is correct is
    the failure this command exists to fix.
    """
    target = server_url(http_port)
    if existing_url == target and existing_key is not UNKNOWN_KEY and existing_key == api_key:
        return []
    cmds = []
    if found_name:
        cmds.append(["claude", "mcp", "remove", "--scope", "user", found_name])
    if not api_key:
        # Never substitute the display placeholder here. `_redact` puts
        # `<apiKey>` in what gets printed; putting it in what gets RUN writes a
        # registration that can never authenticate. Callers refuse before this.
        raise ValueError(f"{name}: refusing to build a registration with no apiKey")
    cmds.append(["claude", "mcp", "add", "--scope", "user", "--transport", "http",
                 server_name(name), target,
                 "--header", f"Authorization: Bearer {api_key}"])
    return cmds


def cmd_register(args, prober):
    vaults, settings = enumerate_vaults()
    chosen, err = select(vaults, args.vault, args.all, require_choice=True)
    if err:
        print(err, file=sys.stderr)
        return EXIT_USAGE
    all_problems = False
    if args.all:
        skipped = unconfigured(vaults)
        if skipped:
            print("Not touched by --all, because config has never named them: "
                  + ", ".join(skipped)
                  + ". Add one with `add-vault`, or act on it explicitly with --vault.")
        gone = missing_configured(vaults)
        for gone_name, gone_path, gone_why in gone:
            print(f"{gone_name}: configured, but not found - {gone_path}: {gone_why}. "
                  "Nothing here can act on it.", file=sys.stderr)
        if gone:
            # A configured vault that has vanished is a problem, not a clean
            # run. Exiting 0 here would report success for a vault the user
            # explicitly put under this plugin and that nothing touched.
            all_problems = True
        if not chosen:
            print("No configured vault could be acted on.", file=sys.stderr)
            return EXIT_PROBLEMS
    registered = mcp_servers()
    if registered is None:
        print("The `claude` CLI is not on PATH, so registration cannot be read or "
              "changed from here.", file=sys.stderr)
        return EXIT_USAGE

    problems = all_problems
    planned = []
    for name in sorted(chosen):
        s = settings[name]
        http_port, _ = ports_of(name, vaults, settings)
        if not s["installed"] or not http_port:
            print(f"{name}: no HTTP port on disk - download and enable Local REST API "
                  f"first (vault_ops.py enable-plugin --vault {name}). Skipped.")
            problems = True
            continue
        if not s["api_key"]:
            # Local REST API writes data.json with its ports before it has
            # generated a key. Registering in that window bakes the display
            # placeholder into the user's real config: a server that can never
            # authenticate, which nothing later re-derives. A missing key is a
            # missing prerequisite, exactly like a missing port.
            print(f"{name}: data.json exists but carries no apiKey yet, so there is "
                  "nothing to register with. The plugin generates its key the first "
                  "time it actually runs - open this vault in Obsidian (relaunch it if "
                  "it is already open), then run this again. Skipped.")
            problems = True
            continue
        found, url = find_registration(registered, name, http_port)
        stored = mcp_server_key(found) if found else None
        if stored is None:
            stored = UNKNOWN_KEY
        cmds = register_commands(name, http_port, s["api_key"], found, url, stored)
        if not cmds:
            print(f"{name}: already registered as {found} -> {url}, and the stored key "
                  "matches this vault's current apiKey.")
            continue
        if url == server_url(http_port):
            why = ("its stored key could not be read back, so whether it still "
                   "authenticates is unknown" if stored is UNKNOWN_KEY
                   else "its stored key no longer matches this vault's apiKey")
            print(f"{name}: registered at the right URL but {why} - re-registering.")
        planned.append((name, cmds))

    if planned:
        print("Planned registration changes (nothing runs without --apply):")
        for name, cmds in planned:
            for cmd in cmds:
                print(f"  {name}: " + " ".join(_redact(cmd)))

    orphans = orphan_servers(registered, vaults, settings)
    if orphans:
        # Reported, never removed. A server whose URL matches no vault is
        # usually one whose vault moved ports (fix-ports does exactly that),
        # and its name may be the legacy `obsidian` that skills and saved
        # prompts already call by hand - so adding the canonical name leaves
        # TWO servers, and this is the line that says so.
        print("\nRegistered obsidian servers that no vault claims:")
        for server, url in orphans:
            print(f"  {server} -> {url}. Adding a canonical entry for that vault does NOT "
                  f"replace this one: remove it with "
                  f"`claude mcp remove --scope user {server}`.")
        problems = True

    if not planned:
        return EXIT_PROBLEMS if problems else EXIT_OK

    if not args.apply:
        print("\nDry run. Re-run with --apply to execute these commands.")
        return EXIT_PROBLEMS

    for name, cmds in planned:
        for cmd in cmds:
            code, ok = run_command(cmd)
            status = "ok" if ok else f"exit {code}"
            print(f"  {name}: {' '.join(_redact(cmd))} -> {status}")
            if not ok:
                problems = True
    return EXIT_PROBLEMS if problems else EXIT_OK


def _redact(cmd):
    """The same command with the bearer token masked - this output gets pasted.

    Masked on the header prefix alone, with no length test: a short key is
    still a key, and a redaction that only fires above some length is one that
    leaks exactly the keys nobody thought to check.
    """
    return ["Authorization: Bearer <apiKey>" if part.startswith("Authorization: Bearer ")
            else part for part in cmd]


# --- enable-plugin -----------------------------------------------------------
#
# This ENABLES a plugin whose files are already on disk. It does not download
# one, and it does not pretend to. An Obsidian community plugin ships as
# unsigned `main.js`, `manifest.json` and `styles.css` on a GitHub release, with
# no publisher signature and no authoritative checksum to check a download
# against. That code runs with the same Electron and Node privileges as Obsidian
# itself, over every note in the vault. Fetching it here would mean writing
# unverifiable executable code into the user's editor and calling it an install,
# which is worse than an exact manual instruction - so the download stays a
# stated prerequisite, and the vaults that need it are named.

MANUAL_INSTALL = (
    "Download is a manual prerequisite - nothing here fetches plugin code. In "
    "Obsidian, with THIS vault open: Settings -> Community plugins -> Turn on "
    "community plugins (leaves Restricted Mode) -> Browse -> search for it -> "
    "Install. Come back and run this command to enable it, or click Enable there. "
    "A plugin generates its own data.json the first time it runs (for Local REST "
    "API that is where the apiKey appears), which is what every other subcommand "
    "here reads."
)


def read_community_plugins(vault_path):
    path = obsidian_common.community_plugins_path(vault_path)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return path, None
    return path, data if isinstance(data, list) else None


def plugin_dir_for(vault_path, plugin_id):
    if plugin_id == REST_PLUGIN_ID:
        return obsidian_common.rest_api_plugin_dir(vault_path)
    return os.path.join(vault_path, ".obsidian", "plugins", plugin_id)


def plugin_state(vault_path, plugin_id, enabled):
    """Where one plugin stands in this vault: (state, detail).

        enabled       listed in community-plugins.json
        has-run       that list is unreadable, but the plugin has written its
                      own data.json, so it demonstrably ran - which is the only
                      honest verdict available when the list cannot be read,
                      and the state a vault whose Restricted Mode was never
                      touched is in
        absent        no plugin folder: nothing here can enable it, because
                      downloading and unpacking a community release means
                      writing an unverified zip into somebody's vault. That is
                      Obsidian's own UI's job, with its signature and version
                      handling.
        no-list       files are present but community-plugins.json cannot be
                      read, so there is no list to add a line to
        installed     files are present, it is not enabled, and it can be
    """
    directory = plugin_dir_for(vault_path, plugin_id)
    if enabled is not None and plugin_id in enabled:
        return "enabled", directory
    data_json = os.path.join(directory, "data.json")
    if enabled is None and os.path.isfile(data_json):
        return "has-run", data_json
    if not os.path.isdir(directory):
        return "absent", directory
    if enabled is None:
        return "no-list", directory
    return "installed", directory


def _profile_for(name, entry, override=None):
    """detect() for one vault, with the config layout and override folded in."""
    return vault_profiles.detect(entry["path"], vault_name=name,
                                 layout=entry.get("layout"), override=override)


def cmd_install_plugin(args, prober):
    """Enable plugins from a vault's profile - named one at a time, never in bulk.

    Bare `--apply` writes the BRIDGE floor and nothing else. That is not a
    conservative default that could be relaxed later: enabling a plugin changes
    what a vault renders and what it depends on, exactly as disabling one does,
    and `optimize.md` has always required a separate yes per plugin for the
    removal side. Handing `--apply` a whole authored profile would enable
    fourteen plugins on one keystroke. Every plugin past the floor is named
    with `--plugin ID`, and the exact command for each is printed here so the
    caller can walk them with the user one at a time.
    """
    vaults, settings = enumerate_vaults()
    chosen, err = select(vaults, args.vault, args.all, require_choice=True)
    if err:
        print(err, file=sys.stderr)
        return EXIT_USAGE
    all_problems = False
    if args.all:
        skipped = unconfigured(vaults)
        if skipped:
            print("Not touched by --all, because config has never named them: "
                  + ", ".join(skipped)
                  + ". Add one with `add-vault`, or act on it explicitly with --vault.")
        gone = missing_configured(vaults)
        for gone_name, gone_path, gone_why in gone:
            print(f"{gone_name}: configured, but not found - {gone_path}: {gone_why}. "
                  "Nothing here can act on it.", file=sys.stderr)
        if gone:
            # A configured vault that has vanished is a problem, not a clean
            # run. Exiting 0 here would report success for a vault the user
            # explicitly put under this plugin and that nothing touched.
            all_problems = True
        if not chosen:
            print("No configured vault could be acted on.", file=sys.stderr)
            return EXIT_PROBLEMS
    if args.profile and args.profile not in vault_profiles.PROFILE_KINDS:
        print(f"unknown profile {args.profile!r} "
              f"(known: {', '.join(vault_profiles.PROFILE_KINDS)})", file=sys.stderr)
        return EXIT_USAGE

    problems = all_problems
    for name in sorted(chosen):
        entry, s = vaults[name], settings[name]
        detected = _profile_for(name, entry, args.profile)
        cp_path, enabled = read_community_plugins(entry["path"])
        comparison = vault_profiles.compare(detected["kind"], detected["evidence"]["notes"],
                                            enabled)
        print(f"{name}: {detected['kind']} profile ({detected['source']}), "
              f"{len(comparison['wanted'])} plugin(s) in the set")
        note = vault_profiles.threshold_note(detected["kind"], detected["evidence"]["notes"])
        if note:
            print(f"  {note}")

        requested = list(args.plugin or [])
        unknown = [p for p in requested if p not in comparison["wanted"]]
        if unknown:
            print(f"  {', '.join(unknown)} is not in the {detected['kind']} profile's set "
                  f"({', '.join(comparison['wanted'])}). Use --profile KIND if the vault's "
                  "kind is wrong; this subcommand only enables what a profile asks for.",
                  file=sys.stderr)
            problems = True
            continue
        # No --plugin: the floor, and only the floor. Everything else in the
        # profile is reported as its own command below.
        targets = requested or [p for p in comparison["missing"] if p == REST_PLUGIN_ID]

        for plugin_id in comparison["wanted"]:
            state, where = plugin_state(entry["path"], plugin_id, enabled)
            if state == "enabled":
                continue
            if state == "has-run":
                print(f"  {plugin_id}: already installed and has run at least once "
                      f"({where}).")
                continue
            if state == "absent":
                # Nothing here can enable a plugin whose files are not on disk,
                # so pointing at `--plugin` would be pointing at a command that
                # can only repeat this message.
                print(f"  {plugin_id}: NOT DOWNLOADED - its files are not at {where}. "
                      f"{vault_profiles.PLUGIN_PURPOSE.get(plugin_id, '')}")
                print(f"    {MANUAL_INSTALL}")
                if plugin_id == vault_profiles.BRIDGE_PLUGIN_ID:
                    print(f"    Until this is done, {name} is invisible to Claude: there "
                          "is no bridge to reach it through, so ports, API key and MCP "
                          "registration all have nothing to act on.")
                problems = True
                continue
            if plugin_id not in targets:
                print(f"  {plugin_id}: MISSING - {vault_profiles.PLUGIN_PURPOSE.get(plugin_id, '')}")
                print(f"    confirm this one on its own, then: vault_ops.py install-plugin "
                      f"--vault {name} --plugin {plugin_id} --apply")
                problems = True
                continue
            if state == "no-list":
                print(f"  {plugin_id}: files are at {where} but {cp_path} is missing or not "
                      "a JSON list - enable it from Obsidian's Community plugins pane "
                      "instead of editing that file by hand.")
                problems = True
                continue

            print(f"  Planned change: add \"{plugin_id}\" to {cp_path}")
            print(f"    before: {json.dumps(enabled)}")
            print(f"    after:  {json.dumps(enabled + [plugin_id])}")
            print(f"    why:    {vault_profiles.PLUGIN_PURPOSE.get(plugin_id, '')}")
            if not args.apply:
                print("  Dry run. Re-run with --apply to write it.")
                problems = True
                continue
            try:
                with open(cp_path, "w", encoding="utf-8") as fh:
                    json.dump(enabled + [plugin_id], fh, indent=2)
                    fh.write("\n")
            except OSError as e:
                print(f"  FAILED to write {cp_path}: {e}", file=sys.stderr)
                problems = True
                continue
            enabled = enabled + [plugin_id]
            # Not "installed". community-plugins.json is read at LAUNCH, not at
            # app:reload - the stale-instance trap that made a port change read
            # as an auth failure applies here too, one layer further out.
            print(f"  wrote {cp_path}. Obsidian reads this file only at launch: quit it from "
                  "the tray icon and relaunch this vault, then re-run `scan` to pick up the "
                  "ports and apiKey the plugin generates on first run. Until that relaunch "
                  "this plugin is enabled on disk and NOT running.")

        if s["installed"] and REST_PLUGIN_ID not in (enabled or []):
            print(f"  Local REST API is already installed ({s['data_path']}) but is NOT "
                  f"listed in {cp_path}.")
    return EXIT_PROBLEMS if problems else EXIT_OK


# --- profile -----------------------------------------------------------------

def profile_report(name, entry, override=None, split=False):
    """The full profile picture for one vault: verdict, evidence, both gaps."""
    detected = _profile_for(name, entry, override)
    _cp_path, enabled = read_community_plugins(entry["path"])
    comparison = vault_profiles.compare(detected["kind"], detected["evidence"]["notes"], enabled)
    out = dict(detected)
    out["comparison"] = comparison
    out["threshold"] = vault_profiles.threshold_note(detected["kind"],
                                                     detected["evidence"]["notes"])
    out["split"] = vault_profiles.split_recommendation(detected["kind"], detected["evidence"],
                                                       comparison)
    out["split_analysis"] = (vault_profiles.split_analysis(entry["path"]) if split else None)
    out["matches"] = (comparison["known"] and not comparison["missing"]
                      and not comparison["unwanted"])
    return out


def print_profile(report):
    ev = report["evidence"]
    print(f"{report['vault']}  ({report['path']})")
    print(f"  kind      {report['kind']}  [{report['source']}]"
          + ("" if report["kind"] == report["detected_kind"]
             else f"   (detection said: {report['detected_kind']})"))
    print(f"  size      {ev['notes']:,} notes, {ev['plugin_count']} community plugin(s)")
    for reason in report["reasons"]:
        print(f"  evidence  - {reason}")
    if report["threshold"]:
        print(f"  threshold {report['threshold']}")
    comparison = report["comparison"]
    if not comparison["known"]:
        print("  NOTE      community-plugins.json is missing or unreadable, so what is "
              "enabled is unknown. Nothing is proposed for REMOVAL from a list nobody "
              "has read.")
    print(f"  wants     {', '.join(comparison['wanted'])}")
    print(f"  lacks     {', '.join(comparison['missing']) or '(nothing)'}")
    carries = ", ".join(comparison["unwanted"]) or "(nothing the profile does not want)"
    print(f"  carries   {carries}")
    for plugin_id in comparison["unwanted"]:
        print(f"    {plugin_id}: not in the {report['kind']} set. Confirm this one on its "
              "own before disabling it - it can be load-bearing for hundreds of notes "
              "through a Dataview query, a Templater template or a Breadcrumbs edge. "
              "`/obsidian-vault:optimize` walks them one at a time.")
    for line in report["split"]:
        print(f"  split     {line}")
    analysis = report["split_analysis"]
    if analysis:
        print(f"  breakage  {analysis['detail']}")
        print("            Nothing is moved by this command. A split needs an explicit yes "
              "per file, and these links do not come back.")


def cmd_profile(args, prober):
    vaults, _settings = enumerate_vaults()
    chosen, err = select(vaults, args.vault)
    if err:
        print(err, file=sys.stderr)
        return EXIT_USAGE
    if not vaults:
        print("No vaults found (nothing configured, and Obsidian's registry is empty).")
        return EXIT_PROBLEMS
    if args.profile and args.profile not in vault_profiles.PROFILE_KINDS:
        print(f"unknown profile {args.profile!r} "
              f"(known: {', '.join(vault_profiles.PROFILE_KINDS)})", file=sys.stderr)
        return EXIT_USAGE

    if args.set:
        return _set_profile(args, vaults)

    reports = [profile_report(name, vaults[name], args.profile, args.split_analysis)
               for name in sorted(chosen)]
    if args.json:
        print(json.dumps({"vaults": reports}, indent=2, default=str))
    else:
        for report in reports:
            print_profile(report)
            print()
    return EXIT_OK if all(r["matches"] for r in reports) else EXIT_PROBLEMS


def _set_profile(args, vaults):
    """`--set KIND` writes an override into config - dry run until --apply.

    `--set auto` clears it and hands the vault back to detection. A stored kind
    is an override of a verdict, not a replacement for one: `profile` keeps
    reporting what detection would have said, so an override that has gone
    stale is visible rather than silently authoritative.
    """
    if not args.vault:
        print("--set needs --vault NAME: a profile override is per vault.", file=sys.stderr)
        return EXIT_USAGE
    kind = None if args.set == "auto" else args.set
    if kind is not None and kind not in vault_profiles.PROFILE_KINDS:
        print(f"unknown profile {args.set!r} (known: "
              f"{', '.join(vault_profiles.PROFILE_KINDS)}, auto)", file=sys.stderr)
        return EXIT_USAGE
    path, before, after = vault_profiles.plan_set_profile(args.vault, kind)
    if (before, after) == (None, None) and vault_profiles.configured_profile(args.vault) is None:
        cfg = obsidian_common.read_config()
        if not isinstance(cfg.get("vaults"), dict) or args.vault not in cfg["vaults"]:
            print(f"{args.vault} has no entry in {path} - run /obsidian-vault:init to give "
                  "it one before an override can be stored against it.", file=sys.stderr)
            return EXIT_USAGE
    detected = _profile_for(args.vault, vaults[args.vault])["detected_kind"]
    print(f"Planned change to {path}:")
    print(f"  vaults.{args.vault}.profile: {before or '(unset)'} -> {after or '(unset)'}")
    print(f"  detection on its own says: {detected}")
    if after and after != detected:
        print("  This override DISAGREES with detection. `profile` keeps reporting both, "
              "so the disagreement stays visible instead of quietly winning.")
    if not args.apply:
        print("\nDry run. Re-run with --apply to write it.")
        return EXIT_PROBLEMS
    try:
        vault_profiles.apply_set_profile(args.vault, kind)
    except (OSError, ValueError) as e:
        print(f"FAILED to write {path}: {e}", file=sys.stderr)
        return EXIT_USAGE
    print(f"wrote {path}. This changes what `profile` and `install-plugin` propose; it "
          "enables and disables nothing on its own.")
    return EXIT_OK


# --- graph-health ------------------------------------------------------------

def graph_vault_name(vaults, requested=None):
    if requested:
        return requested if requested in vaults else None
    candidates = [n for n, e in vaults.items()
                  if (e.get("layout") or "").strip() == "org/repo"]
    return candidates[0] if len(candidates) == 1 else None


def scan_graph_layout(vault_path):
    """(repos, oddities, empties) for an `<org>/<repo>` code-graph vault.

    A code-graph vault is machine-written by `graphify export obsidian --dir
    <vault>/<org>/<repo>`, so its shape is checkable: exactly two levels before
    the notes. Anything else is reported as an oddity rather than an error,
    because a vault legitimately holds hand-made folders too - Obsidian's own
    `inbox/` and `Welcome.md` look exactly like a mis-pointed export from the
    outside. Naming one confident wrong cause is what this whole module exists
    to stop doing, so both possibilities are stated and the reader decides.
    """
    repos, oddities, empties = [], [], []
    try:
        top = sorted(os.listdir(vault_path))
    except OSError as e:
        return repos, [f"cannot read {vault_path}: {e}"], empties
    for org in top:
        if org.startswith("."):
            continue
        org_path = os.path.join(vault_path, org)
        if not os.path.isdir(org_path):
            if org.endswith(".md"):
                oddities.append(f"{org}: a note at the vault root. A graph export never "
                                "writes there; Obsidian's own Welcome.md does.")
            continue
        children = [c for c in sorted(os.listdir(org_path)) if not c.startswith(".")]
        subdirs = [c for c in children if os.path.isdir(os.path.join(org_path, c))]
        notes = [c for c in children if c.endswith(".md")]
        if not children:
            empties.append(org_path)
            continue
        if notes and not subdirs:
            oddities.append(f"{org}/: holds notes directly instead of <org>/<repo> "
                            "subfolders - either an export pointed one level too shallow, "
                            "or a hand-made folder that is not a code graph at all.")
            continue
        for repo in subdirs:
            repo_path = os.path.join(org_path, repo)
            newest, count = 0.0, 0
            for root, _dirs, files in os.walk(repo_path):
                for f in files:
                    if not f.endswith(".md"):
                        continue
                    count += 1
                    try:
                        newest = max(newest, os.path.getmtime(os.path.join(root, f)))
                    except OSError:
                        pass
            if count == 0:
                empties.append(repo_path)
                continue
            repos.append({"org": org, "repo": repo, "path": repo_path,
                          "notes": count, "newest": newest,
                          "age_days": (time.time() - newest) / 86400.0})
    return repos, oddities, empties


def cmd_graph_health(args, prober):
    vaults, _settings = enumerate_vaults()
    name = graph_vault_name(vaults, args.vault)
    if not name:
        print("Name the code-graph vault with --vault NAME: none of the configured vaults "
              "is unambiguously the one with \"layout\": \"org/repo\".", file=sys.stderr)
        return EXIT_USAGE
    vault_path = vaults[name]["path"]
    repos, oddities, empties = scan_graph_layout(vault_path)

    print(f"{name} ({vault_path}): {len(repos)} <org>/<repo> graph(s)")
    stale = [r for r in repos if r["age_days"] > STALE_DAYS]
    for r in sorted(repos, key=lambda r: (r["org"], r["repo"])):
        flag = "STALE" if r["age_days"] > STALE_DAYS else "ok"
        print(f"  [{flag}] {r['org']}/{r['repo']}: {r['notes']} notes, newest "
              f"{r['age_days']:.0f} days old")
    for o in oddities:
        print(f"  [WARN] {o}")
    for r in stale:
        print(f"  Refresh {r['org']}/{r['repo']}: run `graphify update .` in the source "
              "repo, then `graphify export obsidian --graph graphify-out/graph.json --dir "
              f"{r['path']}`")
    if oddities:
        print("  Nothing above is moved automatically. If one of those really is a "
              "mis-pointed export, only the source repo knows its <org> - guessing one "
              "scatters graphs where nobody finds them. Re-run the export with the "
              "correct --dir, then delete the old folder.")

    if empties:
        print(f"\n  {len(empties)} empty folder(s) left behind by an aborted export:")
        for path in empties:
            print(f"    {path}")
        if args.fix:
            for path in empties:
                try:
                    os.rmdir(path)
                    print(f"    removed {path}")
                except OSError as e:
                    print(f"    could not remove {path}: {e}", file=sys.stderr)
        else:
            print("    --fix removes exactly these (empty directories, no notes lost) "
                  "and nothing else.")
    return EXIT_OK if not (oddities or stale or empties) else EXIT_PROBLEMS


# --- add-vault ---------------------------------------------------------------

def cmd_add_vault(args, prober):  # pylint: disable=unused-argument
    """Name a vault in config, so every other subcommand can address it.

    A vault config has never heard of is discovered under its directory
    basename. When the name someone chose differs from the folder - `thd`
    for `claude-anew-thd-codegraph` - then `--vault thd` is an unknown vault on
    every step, and setup cannot proceed at all: enable-plugin, fix-ports and
    register all take the name. Writing the entry is therefore the FIRST step of
    setting a vault up, not a record of it afterwards.
    """
    path = os.path.abspath(os.path.expanduser(args.path))
    if not os.path.isdir(path):
        print(f"no directory at {path}", file=sys.stderr)
        return EXIT_USAGE

    config = obsidian_common.read_config()
    vaults = config.get("vaults")
    vaults = dict(vaults) if isinstance(vaults, dict) else {}
    if not vaults and config.get("vaultPath"):
        # Legacy single-vault shape. Writing a `vaults` block stops the legacy
        # key from being read at all, so carry it across rather than silently
        # unconfiguring the vault that is already working.
        vaults["memory"] = {"path": config["vaultPath"], "default": True}
        print(f"  carrying the legacy vaultPath across as \"memory\" "
              f"({config['vaultPath']}) - a vaults block stops it being read")

    entry = dict(vaults.get(args.name) or {})
    before = dict(entry)
    entry["path"] = path
    if args.port is not None:
        entry["port"] = args.port
    if args.layout:
        entry["layout"] = args.layout
    if args.default:
        for other, existing in vaults.items():
            if other != args.name and isinstance(existing, dict):
                existing.pop("default", None)
        entry["default"] = True
    vaults[args.name] = entry

    verb = "update" if before else "add"
    print(f"Planned config change ({obsidian_common.config_path()}):")
    print(f"  {verb} vaults.{args.name}:")
    for key in sorted(entry):
        was = before.get(key)
        suffix = "" if was is None or was == entry[key] else f"   (was {was!r})"
        print(f"    {key}: {entry[key]!r}{suffix}")
    if not args.apply:
        print("\nDry run. Re-run with --apply to write it.")
        return EXIT_PROBLEMS

    config["vaults"] = vaults
    obsidian_common.write_config(config)
    print(f"wrote {obsidian_common.config_path()}")
    print(f"`--vault {args.name}` now resolves. Do this before enable-plugin, "
          "fix-ports and register, all of which address the vault by name.")
    return EXIT_OK


# --- CLI ---------------------------------------------------------------------

def cli_port(value):
    """A port typed on the command line, rejected rather than repaired.

    `obsidian_common._valid_port` substitutes DEFAULT_PORT for a bad value in a
    config someone already wrote, so a hook survives a typo it did not make.
    That is the wrong answer at the point of entry: silently turning 217123 into
    27123 hands the user a working config for a port they never chose, and it
    reads as success. Same rule, opposite response.
    """
    try:
        port = int(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError(f"{value!r} is not an integer") from None
    if not obsidian_common.port_in_range(port):
        raise argparse.ArgumentTypeError(f"{port} is outside the port range 1-65535")
    return port


def build_parser():
    p = argparse.ArgumentParser(
        prog="vault_ops.py",
        description="Scan, diagnose and repair the Obsidian Local REST API bridge. "
                    "Every writing subcommand is a dry run until --apply.")
    sub = p.add_subparsers(dest="command")

    s = sub.add_parser("scan", help="enumerate every vault: ports, plugin, registration")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_scan)

    s = sub.add_parser("diagnose", help="full health verdict, collisions named first")
    s.add_argument("--vault")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_diagnose)

    s = sub.add_parser("profile", help="which plugin profile this vault is, and the evidence")
    s.add_argument("--vault")
    s.add_argument("--json", action="store_true")
    s.add_argument("--profile", choices=vault_profiles.PROFILE_KINDS,
                   help="override detection for this run only")
    s.add_argument("--set", choices=vault_profiles.PROFILE_KINDS + ("auto",),
                   help="store an override in config (dry run until --apply); "
                        "auto clears it")
    s.add_argument("--split-analysis", action="store_true",
                   help="count the wikilinks a provenance split would break - reads every "
                        "note, so it is off by default")
    s.add_argument("--apply", action="store_true")
    s.set_defaults(func=cmd_profile)

    s = sub.add_parser("fix-ports", help="assign non-colliding ports and write data.json")
    s.add_argument("--vault")
    s.add_argument("--apply", action="store_true")
    s.add_argument("--reload", action="store_true",
                   help="also reload each written vault. Off by default: a reload restarts "
                        "a live Obsidian window, which is a separate yes from editing a "
                        "file on disk. Pass it only once you have that yes.")
    s.set_defaults(func=cmd_fix_ports)

    s = sub.add_parser("reload", help=f"{RELOAD_COMMAND} so a data.json edit takes effect")
    s.add_argument("--vault")
    s.add_argument("--all", action="store_true")
    s.set_defaults(func=cmd_reload)

    s = sub.add_parser("register", help="claude mcp add/remove for each vault")
    s.add_argument("--vault")
    s.add_argument("--all", action="store_true")
    s.add_argument("--apply", action="store_true")
    s.set_defaults(func=cmd_register)

    s = sub.add_parser("enable-plugin", aliases=["install-plugin"],
                       help="ENABLE a vault's profile plugins whose files are already "
                            "on disk - the bridge floor by default, anything further "
                            "only when named with --plugin. Downloading a plugin is a "
                            "manual step in Obsidian; nothing here fetches plugin code")
    s.add_argument("--vault")
    s.add_argument("--all", action="store_true")
    s.add_argument("--profile", choices=vault_profiles.PROFILE_KINDS,
                   help="override detection for this run only")
    s.add_argument("--plugin", action="append", metavar="ID",
                   help="enable exactly this plugin (repeatable). Without it, --apply "
                        "writes only the Local REST API floor - no profile is ever "
                        "enabled in bulk")
    s.add_argument("--apply", action="store_true")
    s.set_defaults(func=cmd_install_plugin)

    s = sub.add_parser("add-vault",
                       help="name a vault in config so --vault <name> resolves. Run "
                            "this FIRST for a new vault: every other subcommand "
                            "addresses a vault by name")
    s.add_argument("--name", required=True)
    s.add_argument("--path", required=True)
    s.add_argument("--port", type=cli_port,
                   help="the vault's HTTP port, if it is known yet (1-65535)")
    s.add_argument("--layout", help="folder convention, e.g. org/repo for a code graph")
    s.add_argument("--default", action="store_true",
                   help="make this the default vault, clearing the flag from any other")
    s.add_argument("--apply", action="store_true")
    s.set_defaults(func=cmd_add_vault)

    s = sub.add_parser("graph-health", help="code-graph vault layout and staleness")
    s.add_argument("--vault")
    s.add_argument("--fix", action="store_true")
    s.set_defaults(func=cmd_graph_health)
    return p


def main(argv=None, prober=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return EXIT_USAGE
    return args.func(args, prober or Prober())


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(EXIT_USAGE)
    except Exception as e:  # pylint: disable=broad-except
        print(f"vault_ops.py: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(EXIT_USAGE)
