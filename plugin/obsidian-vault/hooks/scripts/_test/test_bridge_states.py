#!/usr/bin/env python3
"""Regression suite for the four states a vault's bridge can actually be in.

    python3 hooks/scripts/_test/test_bridge_states.py

The fault this covers: a vault's Obsidian window (2.2 GB resident) exited, and
the symptom - a silent port - was rendered by one line saying "down", which is
exactly what a misconfigured server also produced. Three people each blamed
something different and one was right. So the states are asserted as DISTINCT
verdicts, by constant and not by prose:

    NOT OPEN            no window on this machine names this vault
    NO SERVER           a window is open, nothing is bound
    NOT ANSWERING YET   bound, no usable answer - routinely a plugin indexing,
                        which is NOT a fault and must not read as one
    UP                  answering and authenticated

plus DOWN, CAUSE NOT DETERMINED for the case the evidence does not separate.
Collapsing any two of those five constants into one string is the sabotage
this file was written against, and it goes red on the distinctness cases and
on every case that names its expected verdict.

The second rule under test is the one the shipped version broke: a cause is
only ever stated when this script verified it. The old line blamed
`enableInsecureServer` while the flag was already true on disk, sending the
reader to the one file that was already correct. Several cases here assert
that an unverified cause is NOT named and that the line says what it could not
determine instead.

Nothing here opens a socket, enumerates a window, or needs Obsidian: the
window evidence is a recorded fixture (the two title strings are verbatim
captures from Obsidian 1.13.7) and `listening`/`probe` are monkeypatched, the
same way test_vault_ops.py does it.
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import bridge_status  # noqa: E402  pylint: disable=wrong-import-position
import obsidian_common  # noqa: E402  pylint: disable=wrong-import-position

FAILURES = []

VERDICTS = [bridge_status.VERDICT_NOT_OPEN, bridge_status.VERDICT_NO_SERVER,
            bridge_status.VERDICT_NOT_ANSWERING, bridge_status.VERDICT_UP,
            bridge_status.VERDICT_UNDETERMINED]


def check(desc, got, want):
    if got != want:
        FAILURES.append(f"{desc}: got {got!r}, want {want!r}")


def check_in(desc, needle, haystack):
    if needle.lower() not in haystack.lower():
        FAILURES.append(f"{desc}: {needle!r} not found in {haystack!r}")


def check_not_in(desc, needle, haystack):
    if needle.lower() in haystack.lower():
        FAILURES.append(f"{desc}: {needle!r} should NOT appear in {haystack!r}")


def verdict_of(line):
    """The verdict constant a status line leads with, or None.

    Matched longest-first so a constant that prefixes another cannot mask it,
    and read from the line's own text so that collapsing two constants in
    bridge_status.py makes two different states report the same verdict here.
    """
    _, _, rest_of = line.partition("): ")
    for label in sorted(VERDICTS, key=len, reverse=True):
        if rest_of.startswith(label):
            return label
    return None


# --- Fixtures ----------------------------------------------------------------

def make_vault(root, name, rest_data=None, files=("note.md",)):
    path = os.path.join(root, name)
    os.makedirs(path, exist_ok=True)
    for fname in files:
        with open(os.path.join(path, fname), "w", encoding="utf-8") as fh:
            fh.write(f"# {name} {fname}\n")
    if rest_data is not None:
        plugin_dir = obsidian_common.rest_api_plugin_dir(path)
        os.makedirs(plugin_dir, exist_ok=True)
        with open(os.path.join(plugin_dir, "data.json"), "w", encoding="utf-8") as fh:
            json.dump(rest_data, fh, indent=2)
    return path


def rest(https_port, http_port, api_key, insecure=True):
    return {"port": https_port, "insecurePort": http_port, "apiKey": api_key,
            "enableInsecureServer": insecure, "crypto": {}}


def windows_evidence(vault_names):
    """Recorded Windows evidence: these vault windows are open, no others."""
    return {"method": "windows-window-titles", "window_vaults": list(vault_names),
            "app_running": True if vault_names else None,
            "detail": f"read 40 window titles; Obsidian windows: {', '.join(vault_names)}",
            "cannot": "", "next_check": ""}


def unix_evidence(app_running):
    """Recorded macOS/Linux evidence: process presence only, no window list."""
    return {"method": "linux-proc-comm", "window_vaults": None, "app_running": app_running,
            "detail": ("an Obsidian process is running on this Linux machine" if app_running
                       else "no Obsidian process is running on this Linux machine"),
            "cannot": ("which vault an open window belongs to - Obsidian's process command "
                       "lines name only its user-data directory, never the vault"
                       if app_running else ""),
            "next_check": "look at Obsidian's window list" if app_running else ""}


def line_for(name, vaults, settings, collisions, procs, listening_ports=(), answers=None):
    """One status line with the socket and HTTP layers faked out."""
    old_listening, old_probe = bridge_status.listening, bridge_status.probe
    bridge_status.listening = lambda port, timeout=0.4: port in listening_ports

    def fake_probe(port, api_key, path="/"):
        answer = (answers or {}).get(port)
        if answer is None:
            raise TimeoutError("timed out")
        if isinstance(answer, Exception):
            raise answer
        return answer.get("/vault/" if path == "/vault/" else "/")

    bridge_status.probe = fake_probe
    try:
        return bridge_status.status_line(name, vaults[name], collisions,
                                         {n: v["path"] for n, v in vaults.items()},
                                         settings[name], procs)
    finally:
        bridge_status.listening, bridge_status.probe = old_listening, old_probe


# --- 1. Window titles: what a real Obsidian window actually says --------------

def _t_parse_window_vault():
    # Both strings are verbatim captures from Obsidian 1.13.7 on Windows.
    check("a bare vault window names the vault",
          obsidian_common.parse_window_vault("claude-memories-codegraphs - Obsidian 1.13.7"),
          "claude-memories-codegraphs")
    check("a view/note window still names the vault",
          obsidian_common.parse_window_vault("Graph view - claude-memories - Obsidian 1.13.7"),
          "claude-memories")
    check("a versionless title still parses",
          obsidian_common.parse_window_vault("my-vault - Obsidian"), "my-vault")
    # Everything that is not an Obsidian window must yield nothing, or the
    # attribution is worse than no attribution at all.
    for title in ("Default IME", "MSCTFIME UI", "Obsidian",
                  "Obsidian Publish - Google Chrome", "", None):
        check(f"not an Obsidian vault window: {title!r}",
              obsidian_common.parse_window_vault(title), None)


_t_parse_window_vault()


# --- 2. Attribution: which vault does an open window belong to? ---------------

def _t_window_state():
    tmp = tempfile.mkdtemp(prefix="obsidian-window-test-")
    try:
        mine = make_vault(tmp, "mine")
        other = make_vault(tmp, "other")
        known = {"mine": mine, "other": other}

        state = obsidian_common.vault_window_state(mine, windows_evidence(["mine"]), known)
        check("a window titled with this vault is OPEN",
              state["state"], obsidian_common.WINDOW_OPEN)
        check("an attributed window leaves nothing undetermined", state["cannot"], "")

        state = obsidian_common.vault_window_state(mine, windows_evidence(["other"]), known)
        check("windows listed, none ours, is ABSENT",
              state["state"], obsidian_common.WINDOW_ABSENT)
        check_in("an absent verdict says what it looked at", "other", state["evidence"])

        state = obsidian_common.vault_window_state(mine, windows_evidence([]), known)
        check("no Obsidian window at all is ABSENT",
              state["state"], obsidian_common.WINDOW_ABSENT)

        # macOS/Linux: no window list exists, so attribution is impossible and
        # is reported as impossible rather than guessed either way.
        state = obsidian_common.vault_window_state(mine, unix_evidence(True), known)
        check("a running app with no window list is UNKNOWN",
              state["state"], obsidian_common.WINDOW_UNKNOWN)
        check_in("says what it could not determine", "which vault", state["cannot"])
        check("names the check that would settle it", bool(state["next_check"]), True)

        # The one negative that generalizes: no process, so no window for any
        # vault, on a platform that cannot see windows at all.
        state = obsidian_common.vault_window_state(mine, unix_evidence(False), known)
        check("no Obsidian process anywhere is ABSENT for every vault",
              state["state"], obsidian_common.WINDOW_ABSENT)

        # The enumeration itself failing is a THIRD answer, not "no window".
        broken = {"method": None, "window_vaults": None, "app_running": None,
                  "detail": "the process list could not be read on Linux",
                  "cannot": "whether Obsidian is running at all",
                  "next_check": "a process list"}
        state = obsidian_common.vault_window_state(mine, broken, known)
        check("an unreadable process list is UNKNOWN, not ABSENT",
              state["state"], obsidian_common.WINDOW_UNKNOWN)
        check_in("says the check itself could not run", "could not be read", state["evidence"])

        state = obsidian_common.vault_window_state(mine, None, known)
        check("a check that never ran is UNKNOWN", state["state"],
              obsidian_common.WINDOW_UNKNOWN)
        check_in("says the check was not run", "not run", state["evidence"])

        # Two vaults whose folders share a basename: a window title carries
        # only the folder name, so it cannot say which one is open.
        nested = make_vault(os.path.join(tmp, "second"), "mine")
        ambiguous = {"mine": mine, "twin": nested}
        state = obsidian_common.vault_window_state(mine, windows_evidence(["mine"]), ambiguous)
        check("a shared folder name cannot be attributed",
              state["state"], obsidian_common.WINDOW_UNKNOWN)
        check_in("names the ambiguity", "twin", state["evidence"])
        check_in("says what it could not determine", "which of those vaults", state["cannot"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


_t_window_state()


# --- 3. The four states render as four different verdicts --------------------

def _t_four_states():
    tmp = tempfile.mkdtemp(prefix="obsidian-states-test-")
    try:
        # One vault, four situations. Ports are the real-world shape: HTTPS
        # 27126 BELOW HTTP 27127, so nothing here can be passing by deriving
        # one from the other.
        vault = make_vault(tmp, "solo", rest(27126, 27127, "k-solo"),
                           files=("a.md", "b.md"))
        vaults = {"solo": {"path": vault, "port": None, "layout": None, "default": True}}
        settings = obsidian_common.collect_rest_settings(vaults)
        healthy = {27127: {"/": {"authenticated": True,
                                 "versions": {"obsidian": "1.13.7", "self": "3.1.0"}},
                           "/vault/": {"files": ["a.md", "b.md"]}}}

        # 1. No window names this vault -> NOT OPEN, and not a fault.
        not_open = line_for("solo", vaults, settings, [], windows_evidence(["somewhere-else"]))
        check("no window for this vault is NOT OPEN",
              verdict_of(not_open), bridge_status.VERDICT_NOT_OPEN)
        check_in("NOT OPEN says nothing is expected to listen",
                 "nothing is expected to be listening", not_open)
        check_in("NOT OPEN says it is not a fault", "not a bridge fault", not_open)
        check_in("NOT OPEN says the app may still be resident", "tray", not_open)
        check_not_in("NOT OPEN does not claim the server failed to start",
                     "failed to start", not_open)

        # 2. A window IS open and nothing is bound -> NO SERVER.
        no_server = line_for("solo", vaults, settings, [], windows_evidence(["solo"]))
        check("an open window with no listener is NO SERVER",
              verdict_of(no_server), bridge_status.VERDICT_NO_SERVER)
        # The line quotes the evidence rather than restating it: "a window IS
        # open" in this function's own words would survive the evidence
        # underneath it changing meaning, which is how the shipped
        # enableInsecureServer message came to say something that was not
        # checked.
        check_in("NO SERVER quotes the window evidence", "window is titled 'solo'", no_server)
        check_in("NO SERVER admits it did not find the reason",
                 "did not determine why", no_server)
        check_in("NO SERVER names a check that would find it",
                 "community plugins", no_server)
        # enableInsecureServer is true on disk here. Naming it would repeat the
        # exact bug this file exists to prevent.
        check_not_in("NO SERVER does not blame a flag it did not verify",
                     "enableInsecureServer", no_server)

        # 3. Bound but silent -> NOT ANSWERING YET, and explicitly not a fault.
        indexing = line_for("solo", vaults, settings, [], windows_evidence(["solo"]),
                            listening_ports=(27127,), answers={})
        check("bound but silent is NOT ANSWERING YET",
              verdict_of(indexing), bridge_status.VERDICT_NOT_ANSWERING)
        check_in("says a server IS bound", "a server is bound", indexing)
        check_in("names indexing as a cause", "still building its index", indexing)
        check_in("says indexing is not a fault to fix", "not a fault to fix", indexing)
        check_in("names the other cause too", "wedged", indexing)
        check_in("names the check that separates them", "re-probe", indexing)
        check_in("says a timeout is what it observed", "timed out", indexing)
        # Asserted against the verdict, not against the substring "down":
        # "shut down" or "slowdown" appearing in this prose one day would fail
        # a substring test for a reason that has nothing to do with the state.
        check("a bound-but-silent vault is not reported as a cause-unknown outage",
              verdict_of(indexing) == bridge_status.VERDICT_UNDETERMINED, False)

        # 3b. Same state, different evidence: an immediate refusal is not a
        # timeout, and the line must not weight it as if it were.
        refused = line_for("solo", vaults, settings, [], windows_evidence(["solo"]),
                           listening_ports=(27127,),
                           answers={27127: ConnectionResetError("reset by peer")})
        check("an immediate failure is still NOT ANSWERING YET",
              verdict_of(refused), bridge_status.VERDICT_NOT_ANSWERING)
        check_in("says the probe failed immediately", "failed immediately", refused)
        check_in("says indexing is the less likely reading", "less likely", refused)

        # 4. Answering -> UP.
        up = line_for("solo", vaults, settings, [], windows_evidence(["solo"]),
                      listening_ports=(27127, 27126), answers=healthy)
        check("an answering, authenticated server is UP",
              verdict_of(up), bridge_status.VERDICT_UP)
        check_in("UP names the port it proved", "27127", up)

        # 5. The evidence separates nothing -> say so, name both, name the check.
        undetermined = line_for("solo", vaults, settings, [], unix_evidence(True))
        check("an unattributable window list is UNDETERMINED",
              verdict_of(undetermined), bridge_status.VERDICT_UNDETERMINED)
        check_in("names the closed-vault reading", "not open in obsidian at all", undetermined)
        check_in("names the failed-server reading", "never started", undetermined)
        check_in("says which of the two it could not determine",
                 "not determined", undetermined)
        check_in("names the check that settles it", "window list", undetermined)

        # The whole point: five situations, five different verdicts.
        rendered = [verdict_of(not_open), verdict_of(no_server), verdict_of(indexing),
                    verdict_of(up), verdict_of(undetermined)]
        check("every state is parsed to a known verdict", None in rendered, False)
        check("no two states render as the same verdict", len(set(rendered)), 5)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


_t_four_states()


# --- 4. The port collision still wins, and is still named first --------------

def _t_collision_still_first():
    tmp = tempfile.mkdtemp(prefix="obsidian-states-collision-")
    try:
        # The original fault: both vaults declared HTTPS 27126, the loser's
        # plugin then failed to start its server at all.
        winner = make_vault(tmp, "winner", rest(27126, 27127, "k-win"))
        loser = make_vault(tmp, "loser", rest(27126, 27133, "k-lose"))
        vaults = {"winner": {"path": winner, "port": None, "layout": None, "default": True},
                  "loser": {"path": loser, "port": None, "layout": None, "default": False}}
        settings = obsidian_common.collect_rest_settings(vaults)
        collisions = obsidian_common.find_port_collisions(vaults, settings)
        check("the collision is still detected", len(collisions), 1)

        # (a) The loser's window is open: the collision IS the verified cause,
        #     so it is stated, first, and the fallback list of unverified
        #     causes must not be printed alongside it.
        line = line_for("loser", vaults, settings, collisions,
                        windows_evidence(["loser", "winner"]), listening_ports=(27127,))
        check("an open window with a collision is NO SERVER",
              verdict_of(line), bridge_status.VERDICT_NO_SERVER)
        check_in("the collision is named", "port collision", line)
        check_in("the collision names the port", "27126", line)
        check_in("the collision names the other vault", "winner", line)
        check("the collision leads the explanation, ahead of the advice",
              line.lower().index("port collision") < line.lower().index("mcp__obsidian-"), True)
        check_not_in("a verified cause replaces the list of guesses",
                     "did not determine why", line)
        check_not_in("the collision never blames the insecure-server flag",
                     "enableInsecureServer", line)

        # (b) The window list is unreadable: the collision is still reported
        #     first, but the STATE is still admitted as undetermined.
        line = line_for("loser", vaults, settings, collisions, unix_evidence(True),
                        listening_ports=(27127,))
        check("an unattributable window list is still UNDETERMINED",
              verdict_of(line), bridge_status.VERDICT_UNDETERMINED)
        check_in("the collision is still named", "port collision", line)
        check("the collision leads the explanation",
              line.lower().index("port collision") < line.lower().index("two states fit"), True)
        check_in("and it still says what it could not determine", "not determined", line)

        # (b2) A bound port that stays silent, with a collision on record: the
        #      collision has to come BEFORE "it is probably indexing", or the
        #      reader waits for a server that was never this vault's.
        line = line_for("loser", vaults, settings, collisions,
                        windows_evidence(["loser", "winner"]),
                        listening_ports=(27127, 27133), answers={})
        check("a bound but silent port is still NOT ANSWERING YET",
              verdict_of(line), bridge_status.VERDICT_NOT_ANSWERING)
        check_in("the collision is named there too", "port collision", line)
        check("the collision precedes the indexing reading",
              line.lower().index("port collision")
              < line.lower().index("still building its index"), True)
        check_in("and says the collision must be fixed first", "fix that first", line)

        # (c) Nothing is open anywhere: the collision is a real defect but NOT
        #     the reason this vault is silent, and must not be sold as one.
        line = line_for("loser", vaults, settings, collisions, windows_evidence([]))
        check("no window anywhere is NOT OPEN even with a collision",
              verdict_of(line), bridge_status.VERDICT_NOT_OPEN)
        check_in("the collision is still reported", "port collision", line)
        check_in("but is marked as not the cause", "not the cause of this", line)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


_t_collision_still_first()


# --- 5. A rejected key is the server ANSWERING, not silence ------------------

def _t_key_rejected_is_not_indexing():
    tmp = tempfile.mkdtemp(prefix="obsidian-states-auth-")
    try:
        vault = make_vault(tmp, "keyed", rest(27140, 27141, "k-keyed"))
        vaults = {"keyed": {"path": vault, "port": None, "layout": None, "default": True}}
        settings = obsidian_common.collect_rest_settings(vaults)

        class Unauthorized(Exception):
            code = 401

        line = line_for("keyed", vaults, settings, [], windows_evidence(["keyed"]),
                        listening_ports=(27141,), answers={27141: Unauthorized("401")})
        check_in("a 401 is reported as a rejected key", "rejected", line)
        check("a 401 is not reported as a vault still indexing",
              verdict_of(line) == bridge_status.VERDICT_NOT_ANSWERING, False)
        check_not_in("a 401 must not be sold as 'wait for indexing'", "indexing", line)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


_t_key_rejected_is_not_indexing()


print(f"RESULT: {len(FAILURES)} failed")
for failure in FAILURES:
    print("FAIL:", failure)
sys.exit(1 if FAILURES else 0)
