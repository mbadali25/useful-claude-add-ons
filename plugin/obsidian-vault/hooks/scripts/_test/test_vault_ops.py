#!/usr/bin/env python3
"""Regression suite for the port/collision/identity logic, run without Obsidian.

    python3 hooks/scripts/_test/test_vault_ops.py

Plain assertions, no pytest, same shape as test_obsidian_common.py. Every case
here is built from a fault that actually happened on a real machine:

* Two vaults both declared HTTPS 27126. One won the bind; the loser's Local
  REST API plugin then failed to start its server AT ALL, so its HTTP port
  never listened either, the HTTPS port answered with the OTHER vault's API
  key, and it served the OTHER vault's files. The shipped diagnostic blamed
  `enableInsecureServer`, which was already true on disk.
* `https_port = http_port + 1`. The real pairs on that machine are
  27124/27123, 27128/27125 and 27126/27127 - the last one has HTTPS BELOW
  HTTP, so no derivation in either direction is right. Those exact numbers are
  the fixtures, so reintroducing the derivation goes red on the first case.
* Two vaults had no REST API plugin at all, which is a different verdict from
  "down" and must not be reported as one.

Nothing here opens a socket or shells out: the probe layer is a fake, and the
vaults are directories in a temp folder.
"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import bridge_status  # noqa: E402  pylint: disable=wrong-import-position
import obsidian_common  # noqa: E402  pylint: disable=wrong-import-position
import vault_ops  # noqa: E402  pylint: disable=wrong-import-position
import vault_profiles  # noqa: E402  pylint: disable=wrong-import-position

FAILURES = []


def check(desc, got, want):
    if got != want:
        FAILURES.append(f"{desc}: got {got!r}, want {want!r}")


def check_in(desc, needle, haystack):
    if needle.lower() not in haystack.lower():
        FAILURES.append(f"{desc}: {needle!r} not found in {haystack!r}")


def fail_codes(result):
    return [v["code"] for v in result["verdicts"] if v["level"] == "FAIL"]


def codes_of(result):
    return [v["code"] for v in result["verdicts"]]


def check_not_in(desc, needle, haystack):
    # Case-SENSITIVE, unlike check_in: "this is not a bridge that is down" and
    # "DOWN" are opposite claims, and a case-folding check cannot tell them
    # apart.
    if needle in haystack:
        FAILURES.append(f"{desc}: {needle!r} should NOT appear in {haystack!r}")


# --- Fixtures ----------------------------------------------------------------

def make_vault(root, name, rest_data=None, files=("note.md",)):
    """A vault directory, optionally with a Local REST API data.json.

    rest_data=None means the plugin was never installed - the state two real
    vaults on the reference machine are in, and a verdict of its own.
    """
    path = os.path.join(root, name)
    os.makedirs(path, exist_ok=True)
    for name_ in files:
        with open(os.path.join(path, name_), "w", encoding="utf-8") as fh:
            fh.write(f"# {name} {name_}\n")
    if rest_data is not None:
        plugin_dir = obsidian_common.rest_api_plugin_dir(path)
        os.makedirs(plugin_dir, exist_ok=True)
        with open(os.path.join(plugin_dir, "data.json"), "w", encoding="utf-8") as fh:
            json.dump(rest_data, fh, indent=2)
    return path


def rest(https_port, http_port, api_key, insecure=True):
    """A data.json body. "port" is HTTPS and "insecurePort" is HTTP - the
    naming that makes a skim-read produce the wrong pair."""
    return {"port": https_port, "insecurePort": http_port, "apiKey": api_key,
            "enableInsecureServer": insecure, "crypto": {}}


class Sandbox:
    """A throwaway HOME with a config.json, and a fake Obsidian registry."""

    def __init__(self, vaults_config, app_vaults=None):
        self.tmp = tempfile.mkdtemp(prefix="obsidian-vault-ops-test-")
        self.home = os.path.join(self.tmp, "home")
        os.makedirs(os.path.join(self.home, ".claude", "obsidian"))
        with open(os.path.join(self.home, ".claude", "obsidian", "config.json"),
                  "w", encoding="utf-8") as fh:
            json.dump({"vaults": vaults_config}, fh)
        self.app_vaults = app_vaults or {}
        self._old_home = None
        self._old_env_vault = None
        self._old_app_json = None

    def __enter__(self):
        self._old_home = os.environ.get("HOME")
        self._old_env_vault = os.environ.pop("OBSIDIAN_VAULT_PATH", None)
        os.environ["HOME"] = self.home
        app_json = os.path.join(self.tmp, "obsidian.json")
        with open(app_json, "w", encoding="utf-8") as fh:
            json.dump({"vaults": self.app_vaults}, fh)
        self._old_app_json = obsidian_common.obsidian_app_json_path
        obsidian_common.obsidian_app_json_path = lambda: app_json
        return self

    def __exit__(self, *_exc):
        obsidian_common.obsidian_app_json_path = self._old_app_json
        if self._old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self._old_home
        if self._old_env_vault is not None:
            os.environ["OBSIDIAN_VAULT_PATH"] = self._old_env_vault
        shutil.rmtree(self.tmp, ignore_errors=True)
        return False


class FakeProber:
    """Stands in for Prober: a port map of who is listening and who answers.

    `servers` maps port -> {"key": accepted api key, "files": root listing}.
    A port not in the map is not listening, which is exactly the state a vault
    that lost a port collision is in on BOTH of its ports.
    """

    def __init__(self, servers):
        self.servers = servers
        self.calls = []

    def listening(self, port):
        return bool(port) and port in self.servers

    def get(self, protocol, port, api_key, path="/"):
        return self.request(protocol, port, api_key, path)

    def request(self, protocol, port, api_key, path="/", method="GET"):
        self.calls.append((protocol, port, path, method))
        server = self.servers.get(port)
        if server is None:
            return None, "connection refused"
        if server.get("error"):
            # Listening, but the client could not talk to it - a missing curl
            # on the HTTPS side, or a handshake it refused.
            return None, server["error"]
        if server["key"] != api_key:
            return {"authenticated": False}, None
        if path == "/vault/":
            return {"files": list(server.get("files", []))}, None
        return {"authenticated": True, "versions": {"obsidian": "1.5.0", "self": "3.0.0"}}, None


# --- 1. Ports are READ, never derived ----------------------------------------
# The three real pairs from the reference machine. The third is the one that
# kills any derivation: HTTPS 27126 sits BELOW HTTP 27127.

def _t_ports():
    tmp = tempfile.mkdtemp(prefix="obsidian-ports-test-")
    try:
        memories = make_vault(tmp, "claude-memories", rest(27124, 27123, "k-mem"))
        codegraphs = make_vault(tmp, "claude-memories-codegraphs", rest(27128, 27125, "k-cg"))
        anew = make_vault(tmp, "claude-anew-codegraph", rest(27126, 27127, "k-anew"))
        noplugin = make_vault(tmp, "claude-anew-thd-codegraph", None)

        check("memories ports (http, https)", obsidian_common.resolve_ports(memories),
              (27123, 27124))
        check("codegraphs ports are 3 apart, not adjacent",
              obsidian_common.resolve_ports(codegraphs), (27125, 27128))
        # The sabotage target: `https = http + 1` yields (27127, 27128) here.
        check("anew-codegraph runs HTTPS BELOW HTTP",
              obsidian_common.resolve_ports(anew), (27127, 27126))

        s = obsidian_common.read_rest_settings(anew)
        check("api key is read from the vault's own data.json", s["api_key"], "k-anew")
        check("enableInsecureServer is read as a bool", s["enable_insecure_server"], True)

        s = obsidian_common.read_rest_settings(noplugin)
        check("no data.json means NOT INSTALLED", s["installed"], False)
        check("no data.json means no plugin folder either", s["plugin_dir_present"], False)
        check("no data.json yields no HTTPS port to guess at", s["https_port"], None)
        check("config port is the only HTTP port left",
              obsidian_common.resolve_ports(noplugin, config_port=27199), (27199, None))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


_t_ports()


# --- 2. Collision detection: today's exact fault ------------------------------

def _t_collision():
    tmp = tempfile.mkdtemp(prefix="obsidian-collision-test-")
    try:
        # Both vaults declare HTTPS 27126. "winner" won the bind; "loser"'s
        # plugin never started its server, so neither of its ports listens.
        winner = make_vault(tmp, "winner", rest(27126, 27127, "k-win"),
                            files=("winner-a.md", "winner-b.md"))
        loser = make_vault(tmp, "loser", rest(27126, 27133, "k-lose"),
                           files=("loser-a.md", "loser-b.md"))
        vaults = {"winner": {"path": winner, "port": None, "layout": None, "default": True},
                  "loser": {"path": loser, "port": None, "layout": None, "default": False}}
        settings = obsidian_common.collect_rest_settings(vaults)
        collisions = obsidian_common.find_port_collisions(vaults, settings)

        check("one collision found", len(collisions), 1)
        check("collision is on 27126", collisions[0]["port"], 27126)
        check("both vaults are named as claimants",
              sorted({c["vault"] for c in collisions[0]["claims"]}), ["loser", "winner"])
        check("the loser is matched to the collision",
              len(obsidian_common.collisions_for(collisions, "loser")), 1)

        # The hook line for the loser: down on BOTH protocols, and the reason
        # is the collision - NOT enableInsecureServer, which is true on disk.
        old_listening = bridge_status.listening
        bridge_status.listening = lambda port, timeout=0.4: port == 27127
        try:
            line = bridge_status.status_line("loser", vaults["loser"], collisions,
                                             {n: v["path"] for n, v in vaults.items()},
                                             settings["loser"])
        finally:
            bridge_status.listening = old_listening
        check_in("loser line names the collision", "port collision", line)
        check_in("loser line names the port", "27126", line)
        check_in("loser line names the other vault", "winner", line)
        check_in("loser line says it serves nothing", "serves nothing", line)
        check_not_in("loser line does not blame enableInsecureServer",
                     "enableInsecureServer", line)

        # And the same fault through diagnose(): collision is verdict #1.
        prober = FakeProber({27126: {"key": "k-win", "files": ["winner-a.md", "winner-b.md"]},
                             27127: {"key": "k-win", "files": ["winner-a.md", "winner-b.md"]}})
        result = vault_ops.diagnose_vault("loser", vaults, settings, collisions, prober)
        check("diagnose: loser is unhealthy", result["healthy"], False)
        check("diagnose: collision is the FIRST verdict",
              result["verdicts"][0]["code"], "port-collision")
        check("diagnose: reported ports are the real pair",
              (result["http_port"], result["https_port"]), (27133, 27126))
        codes = [v["code"] for v in result["verdicts"]]
        check("diagnose: a collision is not reported as a plain outage",
              "down" in codes, False)
        check("diagnose: a collision does not blame the insecure-server flag",
              "insecure-server-disabled" in codes, False)

        # fix-ports moves the LOSER, not the vault that is actually serving.
        plan = vault_ops.plan_port_fix(vaults, settings, collisions, prober)
        check("fix-ports plans exactly one move", len(plan), 1)
        check("fix-ports moves the loser", plan[0]["vault"], "loser")
        check("fix-ports moves the HTTPS key", plan[0]["key"], "port")
        check("fix-ports picks a free port", plan[0]["to"] not in (27126, 27127, 27133), True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


_t_collision()


# --- 3. A collision across protocols, not just within one --------------------

def _t_cross_protocol_collision():
    tmp = tempfile.mkdtemp(prefix="obsidian-xproto-test-")
    try:
        a = make_vault(tmp, "a", rest(27130, 27131, "k-a"))
        b = make_vault(tmp, "b", rest(27131, 27140, "k-b"))  # b's HTTPS == a's HTTP
        vaults = {"a": {"path": a, "port": None, "layout": None, "default": True},
                  "b": {"path": b, "port": None, "layout": None, "default": False}}
        settings = obsidian_common.collect_rest_settings(vaults)
        collisions = obsidian_common.find_port_collisions(vaults, settings)
        check("cross-protocol collision is found", len(collisions), 1)
        check("cross-protocol collision port", collisions[0]["port"], 27131)
        protocols = sorted(c["protocol"] for c in collisions[0]["claims"])
        check("both protocols are named", protocols, ["http", "https"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


_t_cross_protocol_collision()


# --- 4. enableInsecureServer false is its OWN verdict ------------------------

def _t_insecure_flag():
    tmp = tempfile.mkdtemp(prefix="obsidian-insecure-test-")
    try:
        off = make_vault(tmp, "off", rest(27150, 27151, "k-off", insecure=False))
        on = make_vault(tmp, "on", rest(27160, 27161, "k-on", insecure=True))
        vaults = {"off": {"path": off, "port": None, "layout": None, "default": True},
                  "on": {"path": on, "port": None, "layout": None, "default": False}}
        settings = obsidian_common.collect_rest_settings(vaults)
        collisions = obsidian_common.find_port_collisions(vaults, settings)
        check("no collision between these two", collisions, [])

        old_listening = bridge_status.listening
        bridge_status.listening = lambda port, timeout=0.4: port in (27150, 27160)
        try:
            off_line = bridge_status.status_line("off", vaults["off"], collisions, {},
                                                 settings["off"])
            on_line = bridge_status.status_line("on", vaults["on"], collisions, {},
                                                settings["on"])
        finally:
            bridge_status.listening = old_listening
        check_in("flag-off line blames the flag", "enableInsecureServer", off_line)
        check_in("flag-off line says which file", "data.json", off_line)
        # The flag is only ever blamed when it is literally false on disk.
        check_in("flag-on line says the flag is already true", "already true", on_line)
        check_in("flag-on line says that is not the cause", "not the cause", on_line)

        prober = FakeProber({27150: {"key": "k-off", "files": ["note.md"]},
                             27160: {"key": "k-on", "files": ["note.md"]}})
        off_result = vault_ops.diagnose_vault("off", vaults, settings, collisions, prober)
        on_result = vault_ops.diagnose_vault("on", vaults, settings, collisions, prober)
        check("diagnose: flag-off has its own code",
              fail_codes(off_result), ["insecure-server-disabled"])
        check("diagnose: flag-on is not blamed on the flag",
              fail_codes(on_result), ["http-down"])
        # The identity check ran and says so: a silent pass would be
        # indistinguishable from a check that never happened.
        check("diagnose: a confirmed identity is stated, not implied",
              "identity-confirmed" in codes_of(off_result), True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


_t_insecure_flag()


# --- 5. Identity: who actually answered? -------------------------------------

def _t_identity():
    tmp = tempfile.mkdtemp(prefix="obsidian-identity-test-")
    try:
        mine = make_vault(tmp, "mine", rest(27170, 27171, "k-mine"),
                          files=("mine-1.md", "mine-2.md", "mine-3.md"))
        theirs = make_vault(tmp, "theirs", rest(27180, 27181, "k-theirs"),
                            files=("theirs-1.md", "theirs-2.md", "theirs-3.md"))
        others = {"theirs": theirs}

        good = obsidian_common.identity_check(mine, ["mine-1.md", "mine-2.md", "mine-3.md"],
                                              others)
        check("matching listing is a match", good["verdict"], "match")

        bad = obsidian_common.identity_check(
            mine, ["theirs-1.md", "theirs-2.md", "theirs-3.md"], others)
        check("foreign listing is a mismatch", bad["verdict"], "mismatch")
        check("the impostor is named", bad["served_vault"], "theirs")

        unknown = obsidian_common.identity_check(mine, [], others)
        check("nothing to compare is 'unknown', not a mismatch",
              unknown["verdict"], "unknown")

        vaults = {"mine": {"path": mine, "port": None, "layout": None, "default": True},
                  "theirs": {"path": theirs, "port": None, "layout": None, "default": False}}
        settings = obsidian_common.collect_rest_settings(vaults)

        # (a) The server on our HTTP port is up, authenticates our key, and
        #     serves the other vault's files.
        prober = FakeProber({27171: {"key": "k-mine",
                                     "files": ["theirs-1.md", "theirs-2.md", "theirs-3.md"]}})
        result = vault_ops.diagnose_vault("mine", vaults, settings, [], prober)
        codes = [v["code"] for v in result["verdicts"]]
        check("diagnose: wrong files is an identity-mismatch",
              "identity-mismatch" in codes, True)
        check("diagnose: an identity mismatch is unhealthy", result["healthy"], False)
        msg = " ".join(v["message"] for v in result["verdicts"])
        check_in("diagnose: the impostor vault is named", "theirs", msg)

        # (b) The exact symptom from the real fault: our key is refused on our
        #     own port, and the OTHER vault's key is accepted there.
        prober = FakeProber({27170: {"key": "k-theirs", "files": ["theirs-1.md"]}})
        result = vault_ops.diagnose_vault("mine", vaults, settings, [], prober)
        msg = " ".join(v["message"] for v in result["verdicts"])
        check("diagnose: foreign key acceptance is an identity mismatch",
              "identity-mismatch" in [v["code"] for v in result["verdicts"]], True)
        check_in("diagnose: says whose key was accepted", "accepts", msg)
        check_in("diagnose: names the owner", "theirs", msg)

        # And the hook says the same thing on its one line.
        old_listening, old_probe = bridge_status.listening, bridge_status.probe
        bridge_status.listening = lambda port, timeout=0.4: port == 27171

        def fake_probe(port, key, path="/"):
            if path == "/vault/":
                return {"files": ["theirs-1.md", "theirs-2.md", "theirs-3.md"]}
            return {"authenticated": True, "versions": {"obsidian": "1.5.0"}}

        bridge_status.probe = fake_probe
        try:
            line = bridge_status.status_line("mine", vaults["mine"], [],
                                             {"mine": mine, "theirs": theirs},
                                             settings["mine"])
        finally:
            bridge_status.listening, bridge_status.probe = old_listening, old_probe
        check_in("hook line reports the wrong vault", "wrong vault", line)
        check_in("hook line names the impostor", "theirs", line)
        check_not_in("hook line does not call it UP", "UP and authenticated", line)

        # (c) A confirmed identity is reported as such...
        prober = FakeProber({27171: {"key": "k-mine",
                                     "files": ["mine-1.md", "mine-2.md", "mine-3.md"]}})
        result = vault_ops.diagnose_vault("mine", vaults, settings, [], prober)
        check("diagnose: a healthy vault says its identity was confirmed",
              "identity-confirmed" in codes_of(result), True)
        check("diagnose: a confirmed identity is still healthy", result["healthy"], True)

        # ...and a check that could not run says so rather than passing quietly.
        # This is the missing-curl case on the HTTPS side: the port listens,
        # nothing answers, and silence would read as approval.
        prober = FakeProber({27170: {"key": "k-mine", "error": "curl not found"}})
        result = vault_ops.diagnose_vault("mine", vaults, settings, [], prober)
        check("diagnose: an unrunnable identity check is a WARN, not silence",
              "identity-unknown" in codes_of(result), True)
        check("diagnose: an unknown identity is not a FAIL",
              "identity-unknown" in fail_codes(result), False)
        msg = " ".join(v["message"] for v in result["verdicts"]
                       if v["code"] == "identity-unknown")
        check_in("diagnose: says why it could not tell", "curl not found", msg)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


_t_identity()


# --- 6. A vault with no plugin is 'not installed', never 'down' --------------

def _t_not_installed():
    tmp = tempfile.mkdtemp(prefix="obsidian-noplugin-test-")
    try:
        bare = make_vault(tmp, "claude-anew-theselectsource", None)
        vaults = {"bare": {"path": bare, "port": 27190, "layout": None, "default": True}}
        settings = obsidian_common.collect_rest_settings(vaults)
        prober = FakeProber({})
        result = vault_ops.diagnose_vault("bare", vaults, settings, [], prober)
        check("diagnose: verdict is plugin-not-installed",
              [v["code"] for v in result["verdicts"]], ["plugin-not-installed"])
        check("diagnose: a missing plugin is not healthy", result["healthy"], False)
        check("diagnose: nothing was probed", prober.calls, [])

        old_listening = bridge_status.listening
        bridge_status.listening = lambda port, timeout=0.4: False
        try:
            line = bridge_status.status_line("bare", vaults["bare"], [], {}, settings["bare"])
        finally:
            bridge_status.listening = old_listening
        check_in("hook line says NOT INSTALLED", "not installed", line)
        check_not_in("hook line does not call it DOWN", "DOWN", line)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


_t_not_installed()


# --- 7. Discovery finds a vault that was never configured --------------------

def _t_discovery():
    tmp = tempfile.mkdtemp(prefix="obsidian-discovery-test-")
    try:
        configured = make_vault(tmp, "memory", rest(27124, 27123, "k-mem"))
        stranger = make_vault(tmp, "claude-anew-codegraph", rest(27126, 27127, "k-anew"))
        with Sandbox({"memory": {"path": configured, "port": 27123, "default": True}},
                     app_vaults={"aaa111": {"path": configured, "ts": 2, "open": True},
                                 "bbb222": {"path": stranger, "ts": 1}}):
            found = obsidian_common.discover_vaults()
            check("configured vault keeps its configured name", "memory" in found, True)
            check("configured vault is marked as known to both",
                  found["memory"]["source"], "both")
            check("the unconfigured vault is discovered anyway",
                  "claude-anew-codegraph" in found, True)
            check("the unconfigured vault is flagged as unconfigured",
                  found["claude-anew-codegraph"]["configured"], False)
            check("discovery does not invent a config port",
                  found["claude-anew-codegraph"]["port"], None)
            settings = obsidian_common.collect_rest_settings(found)
            check("an unconfigured vault's real ports are still read",
                  obsidian_common.resolve_ports(stranger, None, settings["claude-anew-codegraph"]),
                  (27127, 27126))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


_t_discovery()


# --- 8. The CLI contract: subcommands and exit codes -------------------------

def run_cli(argv, prober):
    """(exit_code, stdout). Captured rather than printed: the CLI is chatty by
    design, and what it says is itself under test."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = vault_ops.main(argv, prober)
    return code, out.getvalue()


def _t_cli():
    tmp = tempfile.mkdtemp(prefix="obsidian-cli-test-")
    old_mcp = vault_ops.mcp_servers
    vault_ops.mcp_servers = lambda: None  # never shell out to the real claude CLI
    try:
        a = make_vault(tmp, "alpha", rest(27126, 27127, "k-a"))
        b = make_vault(tmp, "beta", rest(27126, 27133, "k-b"))
        cfg = {"alpha": {"path": a, "port": 27127, "default": True},
               "beta": {"path": b, "port": 27133}}
        prober = FakeProber({})
        with Sandbox(cfg):
            code, out = run_cli(["scan", "--json"], prober)
            check("scan exits 1 when a collision exists", code, vault_ops.EXIT_PROBLEMS)
            payload = json.loads(out)
            check("scan --json reports the real port pair",
                  [(v["http_port"], v["https_port"]) for v in payload["vaults"]],
                  [(27127, 27126), (27133, 27126)])
            check("scan --json reports the collision", payload["collisions"][0]["port"], 27126)

            code, out = run_cli(["diagnose", "--json"], prober)
            check("diagnose exits 1 on problems", code, vault_ops.EXIT_PROBLEMS)
            check("diagnose --json is machine-readable", "vaults" in json.loads(out), True)
            check("diagnose --vault on an unknown vault is a usage error",
                  run_cli(["diagnose", "--vault", "nope"], prober)[0], vault_ops.EXIT_USAGE)

            code, out = run_cli(["fix-ports"], prober)
            check("fix-ports without --apply reports problems", code, vault_ops.EXIT_PROBLEMS)
            check_in("dry run prints the exact change", "27126 -> ", out)
            check_in("dry run names the file it would write", "data.json", out)
            check_in("dry run says nothing was written", "dry run", out)
            after = obsidian_common.read_rest_settings(b)
            check("dry-run fix-ports did not touch data.json", after["https_port"], 27126)

            check("reload with neither --vault nor --all is a usage error",
                  run_cli(["reload"], prober)[0], vault_ops.EXIT_USAGE)
            check("--vault and --all together is a usage error",
                  run_cli(["reload", "--vault", "alpha", "--all"], prober)[0],
                  vault_ops.EXIT_USAGE)
            check("no subcommand at all is a usage error",
                  run_cli([], prober)[0], vault_ops.EXIT_USAGE)
            check("register cannot run without a target",
                  run_cli(["register"], prober)[0], vault_ops.EXIT_USAGE)
            check("install-plugin cannot run without a target",
                  run_cli(["install-plugin"], prober)[0], vault_ops.EXIT_USAGE)

            # --apply writes, and the write is followed by a reload issued
            # against the PRE-write port, which nothing is listening on here.
            code, out = run_cli(["fix-ports", "--apply"], prober)
            check("fix-ports --apply reports the reload it could not deliver",
                  code, vault_ops.EXIT_PROBLEMS)
            check_in("--apply says the write is not yet in effect", "not in effect", out)
            check_in("--apply says a reload is what makes it take effect", "reload", out)
            after = obsidian_common.read_rest_settings(b)
            check("fix-ports --apply moved the colliding HTTPS port",
                  after["https_port"] != 27126, True)
            check("fix-ports --apply left the other settings alone",
                  (after["http_port"], after["api_key"], after["enable_insecure_server"]),
                  (27133, "k-b", True))
            check("the collision is gone afterwards",
                  run_cli(["fix-ports"], prober)[0], vault_ops.EXIT_OK)
    finally:
        vault_ops.mcp_servers = old_mcp
        shutil.rmtree(tmp, ignore_errors=True)


_t_cli()


# --- 9. reload is addressed at the live server, not at disk ------------------

def _t_reload_target():
    tmp = tempfile.mkdtemp(prefix="obsidian-reload-test-")
    try:
        v = make_vault(tmp, "solo", rest(27126, 27127, "k-solo"))
        prober = FakeProber({27127: {"key": "k-solo"}})
        ok, detail = vault_ops.reload_vault("solo", 27127, 27126, "k-solo", prober)
        check("reload succeeds on the HTTP port", ok, True)
        check_in("reload names the command", "app:reload", detail)
        check("reload POSTs the command endpoint",
              prober.calls[-1], ("http", 27127, "/commands/app:reload/", "POST"))

        # Nothing listening: it must say the write is not in effect, not claim success.
        ok, detail = vault_ops.reload_vault("solo", 27199, 27198, "k-solo", FakeProber({}))
        check("reload fails when nothing listens", ok, False)
        check_in("reload says what to do instead", "relaunch", detail)
        check("data.json is untouched by a reload",
              obsidian_common.read_rest_settings(v)["https_port"], 27126)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


_t_reload_target()


# --- 10. Registration is matched by URL, not only by name --------------------
# On the reference machine the memory vault's MCP server is named plain
# `obsidian`, not `obsidian-memory`. A name-only lookup calls it unregistered
# and `register` then proposes a SECOND server on the same port.

def _t_registration_match():
    registered = {"obsidian": "http://127.0.0.1:27123/mcp",
                  "obsidian-codegraphs": "http://127.0.0.1:27125/mcp"}
    found, url = vault_ops.find_registration(registered, "memory", 27123)
    check("a legacy server name is matched by its URL", found, "obsidian")
    check("the matched URL is returned", url, "http://127.0.0.1:27123/mcp")
    # "Already correct" now means the URL AND the stored key match. A URL match
    # with an unreadable key is not evidence of correctness - see test 21.
    check("no commands are proposed for an already-correct server",
          vault_ops.register_commands("memory", 27123, "k", found, url, "k"), [])

    found, url = vault_ops.find_registration(registered, "codegraphs", 27125)
    check("the canonical name still matches", found, "obsidian-codegraphs")

    found, url = vault_ops.find_registration(registered, "anew", 27127)
    check("an unregistered vault is reported as such", (found, url), (None, None))
    cmds = vault_ops.register_commands("anew", 27127, "k-anew", found, url)
    check("an unregistered vault gets exactly one add", len(cmds), 1)
    check("the add uses the canonical name", "obsidian-anew" in cmds[0], True)
    check("the add points at the vault's own HTTP port",
          "http://127.0.0.1:27127/mcp" in cmds[0], True)

    # A server pointing at the wrong port is removed under the name it really
    # has, then re-added - removing "obsidian-memory" here would be a no-op.
    stale = {"obsidian": "http://127.0.0.1:27999/mcp"}
    found, url = vault_ops.find_registration(stale, "memory", 27123)
    check("a stale URL under a legacy name is not matched", found, None)
    cmds = vault_ops.register_commands("memory", 27123, "k", "obsidian",
                                       "http://127.0.0.1:27999/mcp")
    check("a wrong URL is removed then re-added", [c[2] for c in cmds], ["remove", "add"])
    check("the removal targets the name that actually exists", cmds[0][-1], "obsidian")


_t_registration_match()


# --- 10b. register end to end: a legacy name whose vault moved ports ----------
# fix-ports moves the memory vault to 27134. The server registered as plain
# `obsidian` still points at 27123, and `find_registration` (correctly) does not
# match a stale URL under a non-canonical name - so `register` would add
# `obsidian-memory` and leave a second, dead entry behind. It has to say so.

def _t_register_orphan():
    tmp = tempfile.mkdtemp(prefix="obsidian-orphan-test-")
    old_mcp = vault_ops.mcp_servers
    try:
        v = make_vault(tmp, "memory", rest(27135, 27134, "k-mem"))
        vault_ops.mcp_servers = lambda: {"obsidian": "http://127.0.0.1:27123/mcp"}
        with Sandbox({"memory": {"path": v, "port": 27134, "default": True}}):
            code, out = run_cli(["register", "--all"], FakeProber({}))
            check("register reports a problem when a stale entry is left behind",
                  code, vault_ops.EXIT_PROBLEMS)
            check_in("register names the orphaned server", "obsidian ->", out)
            check_in("register says the new entry does not replace it",
                     "does not replace this one", out)
            check_in("register gives the removal command", "claude mcp remove", out)
            check("register plans exactly one add", out.count("mcp add"), 1)
            check_not_in("register never prints a bearer token", "k-mem", out)
    finally:
        vault_ops.mcp_servers = old_mcp
        shutil.rmtree(tmp, ignore_errors=True)


_t_register_orphan()


# --- 10c. install-plugin: the three states a vault can be in -----------------

def _t_install_plugin():
    tmp = tempfile.mkdtemp(prefix="obsidian-install-test-")
    old_mcp = vault_ops.mcp_servers
    vault_ops.mcp_servers = lambda: None
    try:
        absent = make_vault(tmp, "absent", None)
        never_ran = make_vault(tmp, "neverran", None)
        os.makedirs(obsidian_common.rest_api_plugin_dir(never_ran))
        with open(os.path.join(obsidian_common.rest_api_plugin_dir(never_ran), "main.js"),
                  "w", encoding="utf-8") as fh:
            fh.write("// plugin files, never loaded\n")
        cp_path = obsidian_common.community_plugins_path(never_ran)
        os.makedirs(os.path.dirname(cp_path), exist_ok=True)
        with open(cp_path, "w", encoding="utf-8") as fh:
            json.dump(["obsidian-git"], fh)
        done = make_vault(tmp, "done", rest(27146, 27145, "k-done"))

        cfg = {"absent": {"path": absent, "default": True},
               "neverran": {"path": never_ran},
               "done": {"path": done}}
        with Sandbox(cfg):
            code, out = run_cli(["install-plugin", "--vault", "absent"], FakeProber({}))
            check("no plugin files: reports a problem", code, vault_ops.EXIT_PROBLEMS)
            check_in("no plugin files: points at Obsidian's own installer",
                     "community plugins", out)
            check("no plugin files: nothing was written",
                  os.path.exists(obsidian_common.community_plugins_path(absent)), False)

            code, out = run_cli(["install-plugin", "--vault", "neverran"], FakeProber({}))
            check("dry run: reports a problem so nothing looks done",
                  code, vault_ops.EXIT_PROBLEMS)
            check_in("dry run: prints the exact before", '["obsidian-git"]', out)
            check_in("dry run: prints the exact after", '"obsidian-local-rest-api"', out)
            with open(cp_path, "r", encoding="utf-8") as fh:
                check("dry run wrote nothing", json.load(fh), ["obsidian-git"])

            code, out = run_cli(["install-plugin", "--vault", "neverran", "--apply"],
                                FakeProber({}))
            check("--apply succeeds", code, vault_ops.EXIT_OK)
            with open(cp_path, "r", encoding="utf-8") as fh:
                check("--apply enabled the plugin without dropping the others",
                      json.load(fh), ["obsidian-git", "obsidian-local-rest-api"])
            check_in("--apply says a relaunch is what makes it take effect", "relaunch", out)

            code, out = run_cli(["install-plugin", "--vault", "done"], FakeProber({}))
            check("an installed vault is left alone", code, vault_ops.EXIT_OK)
            check_in("an installed vault says so", "already installed", out)
    finally:
        vault_ops.mcp_servers = old_mcp
        shutil.rmtree(tmp, ignore_errors=True)


_t_install_plugin()


# --- 11. graph-health: <org>/<repo> layout and staleness ---------------------

def _t_graph_health():
    tmp = tempfile.mkdtemp(prefix="obsidian-graph-test-")
    try:
        vault = make_vault(tmp, "codegraphs", rest(27128, 27125, "k-cg"), files=())
        fresh = os.path.join(vault, "personal", "useful-claude-add-ons")
        stale = os.path.join(vault, "anew", "SRL")
        os.makedirs(fresh)
        os.makedirs(stale)
        for path, name in ((fresh, "a.md"), (stale, "b.md")):
            with open(os.path.join(path, name), "w", encoding="utf-8") as fh:
                fh.write("# node\n")
        old = time.time() - 40 * 86400
        os.utime(os.path.join(stale, "b.md"), (old, old))
        # A repo exported one level too shallow: notes directly under the org.
        misplaced = os.path.join(vault, "aws-managed-services")
        os.makedirs(misplaced)
        with open(os.path.join(misplaced, "c.md"), "w", encoding="utf-8") as fh:
            fh.write("# stray\n")
        empty = os.path.join(vault, "personal", "abandoned-export")
        os.makedirs(empty)

        repos, oddities, empties = vault_ops.scan_graph_layout(vault)
        check("two <org>/<repo> graphs found", len(repos), 2)
        check("the misplaced repo is reported", len(oddities), 1)
        check_in("it says what the shape is", "instead of <org>/<repo>", oddities[0])
        # Reported as a possibility, not asserted as a cause: a hand-made
        # folder (Obsidian's own inbox/) looks identical from out here.
        check_in("it does not assert a single cause", "or a hand-made folder", oddities[0])
        check("the empty export folder is listed", empties, [empty])
        check("staleness is measured per repo",
              sorted(r["repo"] for r in repos if r["age_days"] > vault_ops.STALE_DAYS),
              ["SRL"])

        with Sandbox({"codegraphs": {"path": vault, "port": 27125,
                                     "layout": "org/repo", "default": True}}):
            code, out = run_cli(["graph-health"], FakeProber({}))
            check("graph-health reports problems", code, vault_ops.EXIT_PROBLEMS)
            check_in("graph-health flags the stale graph", "STALE", out)
            check_in("graph-health names the export command", "graphify export obsidian", out)
            check("graph-health left the empty folder alone without --fix",
                  os.path.isdir(empty), True)
            run_cli(["graph-health", "--fix"], FakeProber({}))
            check("--fix removes the empty export folder", os.path.isdir(empty), False)
            check("--fix does not touch a folder with notes in it",
                  os.path.isdir(misplaced), True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


_t_graph_health()


# --- 14. The three bugs a 788-line suite did not catch ----------------------
# Every case above scoped fix-ports to nothing and reloaded a vault whose first
# protocol answered, so none of these paths was ever entered.

def _t_scoped_fix_and_exhaustion():
    tmp = tempfile.mkdtemp(prefix="obsidian-scoped-test-")
    try:
        # Today's fault: both vaults on HTTPS 27126, "winner" holds the bind.
        winner = make_vault(tmp, "winner", rest(27126, 27127, "k-win"))
        loser = make_vault(tmp, "loser", rest(27126, 27133, "k-lose"))
        vaults = {"winner": {"path": winner, "port": None, "layout": None, "default": True},
                  "loser": {"path": loser, "port": None, "layout": None, "default": False}}
        settings = obsidian_common.collect_rest_settings(vaults)
        collisions = obsidian_common.find_port_collisions(vaults, settings)
        prober = FakeProber({27126: {"key": "k-win"}, 27127: {"key": "k-win"}})

        # Both directions. Scoping to the LOSER moves the loser: that is the
        # vault the user named. Scoping to the HOLDER must NOT quietly edit the
        # loser's file - it refuses and names it. Neither may report nothing to
        # do for a collision the diagnosis just named.
        plan = vault_ops.plan_port_fix(vaults, settings, collisions, prober,
                                       only="loser", allowed={"winner", "loser"})
        check("--vault loser moves the loser", [(s_["vault"], s_.get("blocked"))
                                                for s_ in plan],
              [("loser", None)])

        plan = vault_ops.plan_port_fix(vaults, settings, collisions, prober,
                                       only="winner", allowed={"winner", "loser"})
        check("--vault winner refuses rather than moving the loser",
              [(s_["vault"], s_.get("blocked")) for s_ in plan], [("loser", True)])
        check_in("the refusal names the vault that would have to move",
                 "means moving loser", plan[0]["why"])
        check_in("and says the unscoped run is the fix",
                 "Re-run without --vault", plan[0]["why"])

        # And the unscoped run still actually fixes it.
        plan = vault_ops.plan_port_fix(vaults, settings, collisions, prober,
                                       allowed={"winner", "loser"})
        check("the unscoped run still moves the loser",
              [(s_["vault"], s_.get("blocked")) for s_ in plan], [("loser", None)])

        # A vault not in the collision is still out of scope.
        other = make_vault(tmp, "other", rest(27200, 27201, "k-other"))
        vaults["other"] = {"path": other, "port": None, "layout": None, "default": False}
        settings = obsidian_common.collect_rest_settings(vaults)
        collisions = obsidian_common.find_port_collisions(vaults, settings)
        plan = vault_ops.plan_port_fix(vaults, settings, collisions, prober,
                                       only="other", allowed={"winner", "loser", "other"})
        check("a vault outside the collision plans nothing", plan, [])

        # No replacement port available: refuse, never write None into data.json.
        every_port_busy = FakeProber({p: {"key": "x"} for p in range(27126, 65536)})
        collisions = obsidian_common.find_port_collisions(
            vaults, obsidian_common.collect_rest_settings(vaults))
        plan = vault_ops.plan_port_fix(vaults, settings, collisions, every_port_busy,
                                       allowed={"winner", "loser", "other"})
        check("exhaustion still produces a plan entry", len(plan), 1)
        check("the entry is marked blocked", plan[0].get("blocked"), True)
        check("no port is proposed", plan[0]["to"], None)
        check_in("the refusal says why", "no free port", plan[0]["why"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


_t_scoped_fix_and_exhaustion()


def _t_reload_tries_both_protocols():
    # HTTP is listening but rejects app:reload; HTTPS accepts it. Returning on
    # the first refusal reported a reloadable vault as needing a manual restart.
    prober = FakeProber({27127: {"key": "k-solo", "error": "403 Forbidden"},
                         27126: {"key": "k-solo"}})
    ok, detail = vault_ops.reload_vault("solo", 27127, 27126, "k-solo", prober)
    check("reload falls through to HTTPS after HTTP refuses", ok, True)
    check_in("reload reports the protocol that worked", "HTTPS", detail)

    # Both refuse: report both refusals, not just the first.
    both_wrong = FakeProber({27127: {"key": "k", "error": "403 Forbidden"},
                             27126: {"key": "k", "error": "handshake failed"}})
    ok, detail = vault_ops.reload_vault("solo", 27127, 27126, "k-solo", both_wrong)
    check("reload fails when both protocols refuse", ok, False)
    check_in("the failure names HTTP", "HTTP :27127", detail)
    check_in("the failure names HTTPS too", "HTTPS :27126", detail)


_t_reload_tries_both_protocols()


# --- 15. A mover claiming BOTH protocols must move both ----------------------
# The single-vault branch already handled this shape; the multi-vault path
# picked one key with an any() and left the other half of the collision.

def _t_mover_claims_both_protocols():
    tmp = tempfile.mkdtemp(prefix="obsidian-bothproto-test-")
    try:
        # "winner" holds 27126. "both" claims 27126 on HTTPS *and* HTTP.
        winner = make_vault(tmp, "winner", rest(27126, 27127, "k-win"))
        both = make_vault(tmp, "both", rest(27126, 27126, "k-both"))
        vaults = {"winner": {"path": winner, "port": None, "layout": None, "default": True},
                  "both": {"path": both, "port": None, "layout": None, "default": False}}
        settings = obsidian_common.collect_rest_settings(vaults)
        collisions = obsidian_common.find_port_collisions(vaults, settings)
        prober = FakeProber({27126: {"key": "k-win"}, 27127: {"key": "k-win"}})

        plan = vault_ops.plan_port_fix(vaults, settings, collisions, prober,
                                       allowed={"winner", "both"})
        moved = {(s["vault"], s["key"]) for s in plan}
        check("both of the mover's keys are moved",
              ("both", "port") in moved and ("both", "insecurePort") in moved, True)
        check("the holder is not moved", any(s["vault"] == "winner" for s in plan), False)
        check("the two moves get different ports",
              len({s["to"] for s in plan if s["vault"] == "both"}), 2)
        check("no move lands back on the colliding port",
              any(s["to"] == 27126 for s in plan), False)

        # And the repair actually ends the collision: apply the plan to the
        # fixtures and re-scan. A half-fix leaves 27126 still claimed twice.
        for step in plan:
            vault_ops.write_data_json(settings[step["vault"]]["data_path"],
                                      {step["key"]: step["to"]})
        after = obsidian_common.collect_rest_settings(vaults)
        check("no collision survives the repair",
              obsidian_common.find_port_collisions(vaults, after), [])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


_t_mover_claims_both_protocols()


# --- 16. Applying a port fix does not restart the user's editor --------------
# commands/repair.md promises a reload is asked about separately, because it
# restarts a live window under whoever is typing in it.

def _t_apply_does_not_reload():
    tmp = tempfile.mkdtemp(prefix="obsidian-consent-test-")
    old_mcp = vault_ops.mcp_servers
    vault_ops.mcp_servers = lambda: None  # never shell out to the real claude CLI
    try:
        w = make_vault(tmp, "winner", rest(27126, 27127, "k-win"))
        l = make_vault(tmp, "loser", rest(27126, 27133, "k-lose"))
        cfg = {"winner": {"path": w, "port": 27127, "default": True},
               "loser": {"path": l, "port": 27133}}
        with Sandbox(cfg):
            prober = FakeProber({27126: {"key": "k-win"}, 27127: {"key": "k-win"},
                                 27133: {"key": "k-lose"}})
            code, out = run_cli(["fix-ports", "--apply"], prober)
            reload_calls = [c for c in prober.calls if c[2].startswith("/commands/")]
            check("apply issues no reload without --reload", reload_calls, [])
            check_in("apply says the write is not yet in effect", "NOT in effect", out)
            check_in("apply names the separate reload step", "reload --vault", out)
            check("apply reports the outstanding reload as a problem",
                  code, vault_ops.EXIT_PROBLEMS)

        # With the yes in hand, --reload does perform it. A fresh fixture: the
        # run above already ended the collision, and fix-ports on a healthy
        # machine correctly does nothing at all.
        w2 = make_vault(tmp, "winner2", rest(27126, 27127, "k-win"))
        l2 = make_vault(tmp, "loser2", rest(27126, 27133, "k-lose"))
        cfg2 = {"winner2": {"path": w2, "port": 27127, "default": True},
                "loser2": {"path": l2, "port": 27133}}
        with Sandbox(cfg2):
            prober = FakeProber({27126: {"key": "k-win"}, 27127: {"key": "k-win"},
                                 27133: {"key": "k-lose"}})
            run_cli(["fix-ports", "--apply", "--reload"], prober)
            reload_calls = [c for c in prober.calls if c[2].startswith("/commands/")]
            check("--reload does issue the reload", bool(reload_calls), True)
    finally:
        vault_ops.mcp_servers = old_mcp
        shutil.rmtree(tmp, ignore_errors=True)


_t_apply_does_not_reload()


# --- 17. enable-plugin says what it does, and does not claim to install ------
# The fresh-vault path is its primary scenario and the one it cannot complete:
# a plugin whose files are absent has to be downloaded from inside Obsidian.

def _t_enable_plugin_is_honest():
    tmp = tempfile.mkdtemp(prefix="obsidian-enable-test-")
    old_mcp = vault_ops.mcp_servers
    vault_ops.mcp_servers = lambda: None
    try:
        # A fresh vault: .obsidian exists, no plugins directory at all.
        fresh = os.path.join(tmp, "fresh")
        os.makedirs(os.path.join(fresh, ".obsidian"))
        cfg = {"fresh": {"path": fresh, "default": True}}
        with Sandbox(cfg):
            prober = FakeProber({})
            code, out = run_cli(["enable-plugin", "--vault", "fresh", "--apply"], prober)
            check("a vault with no plugin files is a problem", code, vault_ops.EXIT_PROBLEMS)
            check_in("it says the files are not downloaded", "NOT DOWNLOADED", out)
            check_in("it says nothing here fetches plugin code",
                     "nothing here fetches plugin code", out)
            check_in("it names the manual route", "Community plugins", out)
            check_in("it says the vault is invisible until then", "invisible to Claude", out)
            check_not_in("it does not claim to have installed anything", "installed it", out)

            # The old name still works, so nothing mid-flight breaks.
            code2, out2 = run_cli(["install-plugin", "--vault", "fresh", "--apply"], prober)
            check("install-plugin remains an alias", (code2, "NOT DOWNLOADED" in out2),
                  (vault_ops.EXIT_PROBLEMS, True))
    finally:
        vault_ops.mcp_servers = old_mcp
        shutil.rmtree(tmp, ignore_errors=True)


_t_enable_plugin_is_honest()


# --- 18. A vault is nameable BEFORE the steps that address it by name --------
# discover_vaults() falls back to the directory basename, so a vault whose
# chosen name differs from its folder was unreachable through every --vault step.

def _t_add_vault_makes_the_name_resolve():
    tmp = tempfile.mkdtemp(prefix="obsidian-addvault-test-")
    old_mcp = vault_ops.mcp_servers
    vault_ops.mcp_servers = lambda: None
    try:
        # Directory basename "claude-anew-thd-codegraph", chosen name "thd".
        path = make_vault(tmp, "claude-anew-thd-codegraph", rest(27140, 27141, "k-thd"))
        with Sandbox({}):
            prober = FakeProber({})
            check("the chosen name is unknown before add-vault",
                  run_cli(["diagnose", "--vault", "thd"], prober)[0], vault_ops.EXIT_USAGE)

            code, out = run_cli(["add-vault", "--name", "thd", "--path", path], prober)
            check("add-vault is a dry run without --apply", code, vault_ops.EXIT_PROBLEMS)
            check_in("the dry run shows the entry", "vaults.thd", out)
            check("a dry run writes nothing",
                  run_cli(["diagnose", "--vault", "thd"], prober)[0], vault_ops.EXIT_USAGE)

            code, _ = run_cli(["add-vault", "--name", "thd", "--path", path, "--apply"],
                              prober)
            check("add-vault --apply succeeds", code, vault_ops.EXIT_OK)
            # Exact codes, not "anything but a usage error" - that accepts
            # every remaining code and so passes whatever happened. The vault
            # now resolves AND is unhealthy (nothing is listening on its
            # ports), which is EXIT_PROBLEMS in both cases.
            check("the chosen name now resolves",
                  run_cli(["diagnose", "--vault", "thd"], prober)[0],
                  vault_ops.EXIT_PROBLEMS)
            check("and every by-name step reaches it too",
                  run_cli(["enable-plugin", "--vault", "thd"], prober)[0],
                  vault_ops.EXIT_OK)

        # A legacy single-vault config must not be unconfigured by writing a
        # vaults block: obsidian_common stops reading vaultPath once one exists.
        with Sandbox({}) as _box:
            cfgfile = obsidian_common.config_path()
            legacy = os.path.join(tmp, "legacy-vault")
            os.makedirs(os.path.join(legacy, ".obsidian"), exist_ok=True)
            with open(cfgfile, "w", encoding="utf-8") as fh:
                json.dump({"vaultPath": legacy}, fh)
            run_cli(["add-vault", "--name", "thd", "--path", path, "--apply"], FakeProber({}))
            with open(cfgfile, "r", encoding="utf-8") as fh:
                written = json.load(fh)
            check("the legacy vault is carried across, not dropped",
                  written["vaults"]["memory"]["path"], legacy)
            check("and stays the default", written["vaults"]["memory"].get("default"), True)
    finally:
        vault_ops.mcp_servers = old_mcp
        shutil.rmtree(tmp, ignore_errors=True)


_t_add_vault_makes_the_name_resolve()


# --- 19. No key means no registration, not a placeholder one -----------------
# Local REST API writes data.json and its ports before it has generated an
# apiKey. Registering in that window wrote the literal display placeholder into
# the user's real MCP config: a server that can never authenticate.

def _t_register_refuses_without_a_key():
    tmp = tempfile.mkdtemp(prefix="obsidian-nokey-test-")
    old_mcp = vault_ops.mcp_servers
    old_run = vault_ops.run_command
    ran = []
    vault_ops.mcp_servers = lambda: {}
    # The real execution boundary, replaced. Without this the "no commands were
    # executed" assertion below is vacuous, and a regression that shelled out
    # would both pass the test and invoke the real `claude` on this machine.
    vault_ops.run_command = lambda cmd: (ran.append(cmd), (0, True))[1]
    try:
        # data.json exists with both ports, and apiKey is still empty.
        v = make_vault(tmp, "keyless", rest(27126, 27127, ""))
        cfg = {"keyless": {"path": v, "port": 27127, "default": True}}
        with Sandbox(cfg):
            code, out = run_cli(["register", "--vault", "keyless", "--apply"],
                                FakeProber({}))
            check("a keyless vault is a problem", code, vault_ops.EXIT_PROBLEMS)
            check_in("it says the key is missing", "no apiKey", out)
            check_in("it says how to get one", "Obsidian", out)
            # The proof that matters: nothing was written, and the placeholder
            # never reached a command that would have run.
            check_not_in("no placeholder registration is planned", "<apiKey>", out)
            check_not_in("no mcp add is planned at all", "mcp add", out)
            check("no commands were executed", ran, [])

        # And the builder refuses outright, so no future caller can reintroduce it.
        raised = False
        try:
            vault_ops.register_commands("keyless", 27127, "", None, None)
        except ValueError:
            raised = True
        check("register_commands refuses to build one with no key", raised, True)
    finally:
        vault_ops.mcp_servers = old_mcp
        vault_ops.run_command = old_run
        shutil.rmtree(tmp, ignore_errors=True)


_t_register_refuses_without_a_key()


# --- 21. A rotated key is noticed, not reported as already registered --------
# `claude mcp list` prints name and URL only, so URL equality was being treated
# as proof the stored Bearer token still matched. It is not.

def _t_register_notices_a_rotated_key():
    tmp = tempfile.mkdtemp(prefix="obsidian-rotate-test-")
    old_mcp, old_key, old_run = (vault_ops.mcp_servers, vault_ops.mcp_server_key,
                                 vault_ops.run_command)
    ran = []
    try:
        v = make_vault(tmp, "memory", rest(27124, 27123, "NEW_KEY"))
        cfg = {"memory": {"path": v, "port": 27123, "default": True}}
        vault_ops.mcp_servers = lambda: {"obsidian-memory": "http://127.0.0.1:27123/mcp"}
        vault_ops.run_command = lambda cmd: (ran.append(cmd), (0, True))[1]

        with Sandbox(cfg):
            # Stored key is stale: same URL, different Bearer.
            vault_ops.mcp_server_key = lambda name: "OLD_KEY"
            code, out = run_cli(["register", "--vault", "memory"], FakeProber({}))
            check("a rotated key is a problem, not 'already registered'",
                  code, vault_ops.EXIT_PROBLEMS)
            check_in("it says the stored key no longer matches",
                     "no longer matches", out)
            check_in("a re-registration is actually planned", "mcp add", out)
            check_in("the stale server is removed first", "mcp remove", out)
            check_not_in("it does not claim the key matches", "matches this vault's "
                         "current apiKey", out)

            # Matching key: genuinely nothing to do.
            vault_ops.mcp_server_key = lambda name: "NEW_KEY"
            code, out = run_cli(["register", "--vault", "memory"], FakeProber({}))
            check("a matching key needs no change", code, vault_ops.EXIT_OK)
            check_in("and says the key matched", "stored key matches", out)
            check_not_in("nothing is planned", "mcp add", out)

            # Unreadable key: re-register rather than assume.
            vault_ops.mcp_server_key = lambda name: None
            code, out = run_cli(["register", "--vault", "memory"], FakeProber({}))
            check("an unreadable key re-registers", code, vault_ops.EXIT_PROBLEMS)
            check_in("and says why", "could not be read back", out)

        # The builder itself, directly: URL equality alone is never enough.
        check("URL match with an unknown key still plans a change",
              bool(vault_ops.register_commands("memory", 27123, "NEW_KEY",
                                               "obsidian-memory",
                                               "http://127.0.0.1:27123/mcp")), True)
        check("URL match with the same key plans nothing",
              vault_ops.register_commands("memory", 27123, "NEW_KEY", "obsidian-memory",
                                          "http://127.0.0.1:27123/mcp", "NEW_KEY"), [])
    finally:
        vault_ops.mcp_servers, vault_ops.mcp_server_key = old_mcp, old_key
        vault_ops.run_command = old_run
        shutil.rmtree(tmp, ignore_errors=True)


_t_register_notices_a_rotated_key()


# --- 22. --all means every CONFIGURED vault, not every vault on the disk -----

def _t_all_does_not_reach_unconfigured_vaults():
    tmp = tempfile.mkdtemp(prefix="obsidian-allscope-test-")
    old_mcp, old_key, old_run = (vault_ops.mcp_servers, vault_ops.mcp_server_key,
                                 vault_ops.run_command)
    ran = []
    try:
        mem = make_vault(tmp, "memory", rest(27124, 27123, "k-mem"))
        journal = make_vault(tmp, "private-journal", rest(27130, 27131, "k-journal"))
        vault_ops.mcp_servers = lambda: {}
        vault_ops.mcp_server_key = lambda name: None
        vault_ops.run_command = lambda cmd: (ran.append(cmd), (0, True))[1]

        # Config knows only `memory`; Obsidian's own registry knows both.
        cfg = {"memory": {"path": mem, "port": 27123, "default": True}}
        app = {"vid-journal": {"path": journal, "ts": 1}}
        with Sandbox(cfg, app_vaults=app):
            names = set(vault_ops.enumerate_vaults()[0])
            check("the journal is still DISCOVERED, so collisions stay visible",
                  "private-journal" in names, True)

            code, out = run_cli(["register", "--all", "--apply"], FakeProber({}))
            joined = " ".join(" ".join(c) for c in ran)
            check("nothing was written for the unconfigured vault",
                  "private-journal" in joined, False)
            check("the configured vault was still acted on",
                  "obsidian-memory" in joined, True)
            check_in("the skipped vault is named, not silently dropped",
                     "private-journal", out)
            check_in("and says how to include it", "add-vault", out)
            # The exact code for THIS fixture: one configured vault registered
            # cleanly, one unconfigured vault skipped by design, nothing missing.
            # `code in (OK, PROBLEMS)` accepted every non-usage code register
            # can return, so it passed whatever happened.
            check("register --all exits clean for this fixture",
                  code, vault_ops.EXIT_OK)

            # --vault is explicit consent, so it still reaches the journal.
            chosen, err = vault_ops.select(vault_ops.enumerate_vaults()[0],
                                           name="private-journal")
            check("--vault names it explicitly and is allowed", (err, list(chosen)),
                  (None, ["private-journal"]))
    finally:
        vault_ops.mcp_servers, vault_ops.mcp_server_key = old_mcp, old_key
        vault_ops.run_command = old_run
        shutil.rmtree(tmp, ignore_errors=True)


_t_all_does_not_reach_unconfigured_vaults()


# --- 23. The structural fallback reports counts it actually checked ----------

def _t_structural_fallback_does_not_assert_zero():
    tmp = tempfile.mkdtemp(prefix="obsidian-fallback-test-")
    try:
        # org/repo shaped, well over the note floor, ONE authored plugin on, and
        # a frontmatter ratio under the authored threshold. Previously this said
        # "0 of N" and "no plugin from the authored set is enabled" - both false.
        root = os.path.join(tmp, "mixed")
        for repo in ("orgA/repo1", "orgA/repo2", "orgB/repo3"):
            os.makedirs(os.path.join(root, repo), exist_ok=True)
            for i in range(400):
                with open(os.path.join(root, repo, f"n{i}.md"), "w", encoding="utf-8") as fh:
                    fh.write("# plain\n")
        os.makedirs(os.path.join(root, ".obsidian"), exist_ok=True)
        with open(os.path.join(root, ".obsidian", "community-plugins.json"),
                  "w", encoding="utf-8") as fh:
            json.dump(["dataview"], fh)

        result = vault_profiles.detect(root, vault_name="mixed")
        blob = " ".join(result["reasons"])
        check_not_in("it no longer claims no authored plugin is enabled",
                     "no plugin from the authored set is enabled", blob)
        check_in("it names the authored plugin it actually found", "dataview", blob)
        # "0 of 40" here is a real measurement and is fine. What was wrong was
        # asserting it without checking, and asserting the plugin count too - so
        # the frontmatter line must now cite the sample it actually took.
        check_in("the frontmatter line cites the sample size it took", "of 40 sampled", blob)
        check_in("and says which threshold that is under", "an authored vault shows", blob)
        check("an authored plugin makes the graph verdict unconfident",
              result["confident"], False)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


_t_structural_fallback_does_not_assert_zero()


# --- 20. A port typed by a person is rejected, never repaired ----------------

def _t_port_is_validated_at_entry():
    tmp = tempfile.mkdtemp(prefix="obsidian-portval-test-")
    try:
        path = make_vault(tmp, "somevault", rest(27140, 27141, "k"))
        with Sandbox({}):
            for bad in ("217123", "0", "65536", "-1", "notanumber"):
                raised = False
                try:
                    run_cli(["add-vault", "--name", "v", "--path", path,
                             "--port", bad, "--apply"], FakeProber({}))
                except SystemExit as e:
                    raised = e.code != 0
                check(f"--port {bad} is rejected", raised, True)
                # Sandbox always creates the config file, so the proof is that
                # no entry was written into it, not that the file is absent.
                check(f"--port {bad} wrote no vault entry",
                      "v" in (obsidian_common.read_config().get("vaults") or {}), False)

            # The valid one still works.
            code, _ = run_cli(["add-vault", "--name", "v", "--path", path,
                               "--port", "27141", "--apply"], FakeProber({}))
            check("a valid port is accepted", code, vault_ops.EXIT_OK)

        # The one rule, both directions: config repair keeps its fallback,
        # because a hook must survive a typo it did not make.
        check("an already-written bad config still falls back",
              obsidian_common._valid_port(999999, "test"),  # pylint: disable=protected-access
              obsidian_common.DEFAULT_PORT)
        check("and port_in_range is what both consult",
              [obsidian_common.port_in_range(x) for x in (0, 1, 65535, 65536, True, "8")],
              [False, True, True, False, False, False])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


_t_port_is_validated_at_entry()


# --- 24. fix-ports is the acting command that never calls select() ----------
# It edits a vault's OWN data.json, so the consent rule matters more here than
# it did for the MCP config, not less.

def _t_fix_ports_refuses_an_unconfigured_mover():
    tmp = tempfile.mkdtemp(prefix="obsidian-fixscope-test-")
    try:
        mem = make_vault(tmp, "memory", rest(27126, 27123, "k-mem"))
        journal = make_vault(tmp, "private-journal", rest(27126, 27131, "k-journal"))
        cfg = {"memory": {"path": mem, "port": 27123, "default": True}}
        app = {"vid-journal": {"path": journal, "ts": 1}}
        with Sandbox(cfg, app_vaults=app):
            # memory answers on 27126, so the planner picks the journal as mover.
            prober = FakeProber({27126: {"key": "k-mem"}, 27123: {"key": "k-mem"}})
            before = obsidian_common.read_rest_settings(journal)["https_port"]

            code, out = run_cli(["fix-ports", "--apply"], prober)
            check("an unconfigured mover makes this a problem",
                  code, vault_ops.EXIT_PROBLEMS)
            check_in("the refusal names the vault", "private-journal", out)
            check_in("and names the opt-in route", "add-vault", out)
            check_in("it is shown as refused, not planned", "REFUSED", out)
            check("nothing was written to the unconfigured vault's data.json",
                  obsidian_common.read_rest_settings(journal)["https_port"], before)
            check("the configured vault was not moved instead",
                  obsidian_common.read_rest_settings(mem)["https_port"], 27126)

        # Opted in, the same collision is fixable.
        cfg2 = dict(cfg)
        cfg2["private-journal"] = {"path": journal, "port": 27131}
        with Sandbox(cfg2, app_vaults=app):
            prober = FakeProber({27126: {"key": "k-mem"}, 27123: {"key": "k-mem"}})
            vaults2, settings2 = vault_ops.enumerate_vaults()
            plan = vault_ops.plan_port_fix(
                vaults2, settings2,
                obsidian_common.find_port_collisions(vaults2, settings2), prober)
            check("once configured, the journal is moved",
                  [(s["vault"], s.get("blocked")) for s in plan],
                  [("private-journal", None)])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


_t_fix_ports_refuses_an_unconfigured_mover()


# --- 25. The mcp get parser, against real captured output --------------------
# The registration tests stub mcp_server_key(), so nothing exercised the parser
# itself. This is the verbatim shape `claude mcp get obsidian` printed on
# 2026-09-05, plus the shapes that must NOT be read as a key.

def _t_mcp_get_parser():
    real = (
        "obsidian:\n"
        "  Scope: User config (available in all your projects)\n"
        "  Status: ✔ Connected\n"
        "  Type: http\n"
        "  URL: http://127.0.0.1:27123/mcp\n"
        "  Headers:\n"
        "    Authorization: Bearer "
        "08618c73756324d3f9e4c099e712078eeca48a6f2dfa882125837df1d92d4638\n"
        "\nTo remove this server, run: claude mcp remove obsidian -s user\n"
    )
    check("the real format yields the token",
          vault_ops.parse_mcp_get_key(real),
          "08618c73756324d3f9e4c099e712078eeca48a6f2dfa882125837df1d92d4638")
    check("no Headers block yields no key",
          vault_ops.parse_mcp_get_key("obsidian:\n  Type: http\n  URL: http://x/mcp\n"),
          None)
    check("empty output yields no key", vault_ops.parse_mcp_get_key(""), None)
    check("a header with no value yields no key",
          vault_ops.parse_mcp_get_key("  Headers:\n    Authorization: Bearer\n"), None)

    # Redaction is not a key. It does not happen on this machine today; if a
    # future release starts, this must read as UNKNOWN rather than as a rotated
    # key, or every run would rewrite a correct registration.
    for masked in ("[REDACTED]", "<redacted>", "********", "***"):
        check(f"a {masked} header is unknown, not a key",
              vault_ops.parse_mcp_get_key(f"  Headers:\n    Authorization: Bearer {masked}\n"),
              None)

    # And unknown routes to re-registration, never to a false match.
    check("an unknown key never reports the server as current",
          bool(vault_ops.register_commands("memory", 27123, "REAL", "obsidian-memory",
                                           "http://127.0.0.1:27123/mcp",
                                           vault_ops.UNKNOWN_KEY)), True)


_t_mcp_get_parser()


# --- 26. A configured vault that has vanished is not a clean run -------------

def _t_missing_configured_vault_is_a_problem():
    tmp = tempfile.mkdtemp(prefix="obsidian-missing-test-")
    old_mcp, old_key, old_run = (vault_ops.mcp_servers, vault_ops.mcp_server_key,
                                 vault_ops.run_command)
    ran = []
    try:
        gone_path = os.path.join(tmp, "on-an-unmounted-drive")
        vault_ops.mcp_servers = lambda: {}
        vault_ops.mcp_server_key = lambda name: None
        vault_ops.run_command = lambda cmd: (ran.append(cmd), (0, True))[1]

        # The ONLY configured vault has a path that does not exist.
        with Sandbox({"archive": {"path": gone_path, "port": 27150, "default": True}}):
            code, _out = run_cli(["register", "--all", "--apply"], FakeProber({}))
            check("an empty selection does not exit 0", code, vault_ops.EXIT_PROBLEMS)
            check("nothing was registered", ran, [])
            # stderr is where the per-vault reason goes; the API is asserted
            # directly below rather than through captured output.
            check("the vanished vault is reported by name",
                  [n for n, _p, _w in
                   vault_ops.missing_configured(vault_ops.enumerate_vaults()[0])],
                  ["archive"])

        # Present configured vault + vanished one: the present one still works,
        # and the run is still a problem because the other could not be acted on.
        live = make_vault(tmp, "memory", rest(27124, 27123, "k-mem"))
        with Sandbox({"memory": {"path": live, "port": 27123, "default": True},
                      "archive": {"path": gone_path, "port": 27150}}):
            ran.clear()
            code, _ = run_cli(["register", "--all", "--apply"], FakeProber({}))
            joined = " ".join(" ".join(c) for c in ran)
            check("the live vault is still acted on", "obsidian-memory" in joined, True)
            check("but the vanished one keeps the exit non-zero",
                  code, vault_ops.EXIT_PROBLEMS)
            check("missing_configured names it and says why",
                  [(n, "not exist" in why) for n, _p, why in
                   vault_ops.missing_configured(vault_ops.enumerate_vaults()[0])],
                  [("archive", True)])
    finally:
        vault_ops.mcp_servers, vault_ops.mcp_server_key = old_mcp, old_key
        vault_ops.run_command = old_run
        shutil.rmtree(tmp, ignore_errors=True)


_t_missing_configured_vault_is_a_problem()


# --- 27. A refusal names the field that actually collides -------------------
# The refusal hardcoded "port", which the printer labels HTTPS - so a collision
# that exists only on insecurePort was refused for a change nobody contemplated.

def _t_refusal_names_the_real_key():
    tmp = tempfile.mkdtemp(prefix="obsidian-refusalkey-test-")
    try:
        # Distinct HTTPS ports; both vaults collide on HTTP 27123 only.
        mem = make_vault(tmp, "memory", rest(27124, 27123, "k-mem"))
        journal = make_vault(tmp, "private-journal", rest(27140, 27123, "k-journal"))
        vaults = {"memory": {"path": mem, "port": None, "layout": None, "default": True},
                  "private-journal": {"path": journal, "port": None, "layout": None,
                                      "default": False}}
        settings = obsidian_common.collect_rest_settings(vaults)
        collisions = obsidian_common.find_port_collisions(vaults, settings)
        prober = FakeProber({27123: {"key": "k-mem"}})

        plan = vault_ops.plan_port_fix(vaults, settings, collisions, prober,
                                       allowed={"memory"})
        check("the unconfigured vault is refused",
              [(s_["vault"], s_.get("blocked")) for s_ in plan],
              [("private-journal", True)])
        check("the refusal names insecurePort, not port", plan[0]["key"], "insecurePort")
        check("so the printed label is HTTP",
              "HTTPS" if plan[0]["key"] == "port" else "HTTP", "HTTP")

        # A vault colliding on BOTH protocols is refused for both, not one.
        both = make_vault(tmp, "both", rest(27123, 27123, "k-both"))
        vaults["both"] = {"path": both, "port": None, "layout": None, "default": False}
        settings = obsidian_common.collect_rest_settings(vaults)
        collisions = obsidian_common.find_port_collisions(vaults, settings)
        plan = vault_ops.plan_port_fix(vaults, settings, collisions, prober,
                                       allowed={"memory"})
        check("both of an unconfigured vault's claims are refused",
              sorted(s_["key"] for s_ in plan if s_["vault"] == "both"),
              ["insecurePort", "port"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


_t_refusal_names_the_real_key()


# --- 28. A vault configured with no path says so ----------------------------
# The reason was decided from a display string that is never empty, so the
# no-path branch was unreachable and {} was reported as a deleted directory.

def _t_no_path_recorded():
    tmp = tempfile.mkdtemp(prefix="obsidian-nopath-test-")
    try:
        with Sandbox({"archive": {}}):
            rows = vault_ops.missing_configured({})
            check("the pathless vault is reported", [n for n, _p, _w in rows], ["archive"])
            check("and the reason is that nothing was recorded",
                  "no path recorded" in rows[0][2], True)
            check("it is NOT reported as a deleted directory",
                  "deleted" in rows[0][2], False)

        # A recorded-but-absent path still reports as absent.
        with Sandbox({"archive": {"path": os.path.join(tmp, "gone")}}):
            rows = vault_ops.missing_configured({})
            check("an absent recorded path reports as absent",
                  "does not exist" in rows[0][2], True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


_t_no_path_recorded()


# --- 29. A printed FAIL and a success exit cannot both be true --------------
# diagnose prints every collision on the machine, which is the point of a wide
# diagnosis - but the exit code is scoped, so the label has to be too.

def _t_diagnose_labels_match_the_scope():
    tmp = tempfile.mkdtemp(prefix="obsidian-scopelabel-test-")
    try:
        mem = make_vault(tmp, "memory", rest(27124, 27123, "k-mem"))
        j_a = make_vault(tmp, "journal-a", rest(27126, 27140, "k-a"))
        j_b = make_vault(tmp, "journal-b", rest(27126, 27141, "k-b"))
        cfg = {"memory": {"path": mem, "port": 27123, "default": True},
               "journal-a": {"path": j_a, "port": 27140},
               "journal-b": {"path": j_b, "port": 27141}}
        with Sandbox(cfg):
            # memory is healthy and answering; the two journals collide on 27126.
            prober = FakeProber({27123: {"key": "k-mem", "files": ["note.md"]},
                                 27124: {"key": "k-mem", "files": ["note.md"]}})

            code, out = run_cli(["diagnose", "--vault", "memory"], prober)
            check_in("the unrelated collision is still printed", "27126", out)
            check_in("but it is not labelled a failure", "[ELSEWHERE]", out)
            check_not_in("no FAIL is printed for it", "[FAIL]", out)
            check_in("and it names whose it is", "journal-a", out)
            check("a healthy scoped vault exits 0", code, vault_ops.EXIT_OK)

            # Scoped to a vault that IS in the collision: FAIL, non-zero.
            code, out = run_cli(["diagnose", "--vault", "journal-a"], prober)
            check_in("a collision in scope is a FAIL", "[FAIL]", out)
            check_not_in("and is not labelled elsewhere", "[ELSEWHERE]", out)
            check("and it exits non-zero", code, vault_ops.EXIT_PROBLEMS)

            # The JSON path must not be able to reach the contradiction either.
            code, out = run_cli(["diagnose", "--vault", "memory", "--json"], prober)
            payload = json.loads(out)
            check("json carries the same scope flag",
                  [c["in_scope"] for c in payload["collisions"]], [False])
            check("json exit agrees with its own flags", code, vault_ops.EXIT_OK)
            _, out = run_cli(["diagnose", "--vault", "journal-a", "--json"], prober)
            check("an in-scope collision is flagged in json",
                  [c["in_scope"] for c in json.loads(out)["collisions"]], [True])

            # Unscoped: every collision is in scope, so nothing is ELSEWHERE.
            code, out = run_cli(["diagnose"], prober)
            check_in("unscoped still prints FAIL", "[FAIL]", out)
            check_not_in("unscoped never says elsewhere", "[ELSEWHERE]", out)
            check("unscoped exits non-zero", code, vault_ops.EXIT_PROBLEMS)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


_t_diagnose_labels_match_the_scope()


print(f"RESULT: {len(FAILURES)} failed")
for failure in FAILURES:
    print("FAIL:", failure)
sys.exit(1 if FAILURES else 0)
