#!/usr/bin/env python3
"""SessionStart probe for every configured vault's Local REST API bridge.

Generalized from a personal ~/.claude/hooks/obsidian-bridge-status.py: the
vault list now comes from obsidian_common.list_vaults() instead of one
hardcoded vault, so a machine with a second vault (e.g. a graphify code-graph
vault on its own port) gets its own line rather than being silently ignored.
Local REST API is per-vault - each vault that is actually open in its own
Obsidian window gets its own port, so there is no single bridge to probe.

The failure this exists to prevent: the MCP client can look healthy while
Obsidian is not actually listening, because Obsidian reads its plugin list
only at launch and closing the window merely minimizes it to the tray. Claude
then assumes mcp__obsidian-<name>__* works and stalls when it does not.

Both ports come from the vault's own data.json ("port" is HTTPS, "insecurePort"
is HTTP) and neither is derived from the other. An earlier version computed
`https_port = http_port + 1`, which is wrong on every vault of the machine this
was written for - one of them runs HTTPS *below* HTTP - and that wrong pair is
what let a duplicate-port fault go undiagnosed. Ports are checked for a
collision across every vault on the machine BEFORE any per-vault setting is
blamed, because a collision knocks the losing vault out on both protocols at
once and each of its symptoms has a convincing wrong explanation of its own.

"Down" is not one state, and reporting it as one is what cost three people a
day. Four states produce a silent or unhelpful port, and each needs a
different response (or none at all):

  1. NOT OPEN     - no Obsidian window on this machine names this vault.
  2. NO SERVER    - a window IS open for it, but nothing is bound. The
                    plugin's server never started; a port collision is one
                    cause and is detected here, and there are others.
  3. NOT ANSWERING YET - the port accepts connections, so a server is bound,
                    but the API has not answered. On a large vault this is
                    routinely a plugin still building its index, which is NOT
                    a fault to fix and must never be reported as one.
  4. UP           - answering and authenticated.

A fifth line exists for when the evidence does not pick one of those out:
DOWN, CAUSE NOT DETERMINED, which names the causes that remain open and the
check that separates them. That is deliberate. The shipped version of this
file stated a cause confidently and was wrong - it blamed enableInsecureServer
while the flag was already true on disk, sending the reader to the one file
that was already correct. A confident wrong cause costs more than an admitted
gap, so nothing here asserts a cause this script did not verify.

This states the ground truth up front. It never blocks a session - SessionStart
hooks cannot block, and even if they could, "the bridge is down" is
information, not a reason to refuse the turn.

SessionStart fires once per interpreter that is actually present on the
machine, which on Windows is normally both bash (Git Bash) and PowerShell.
Only one is meant to speak: a claim file per session id, mirroring the pattern
platform-sync.py uses in the crew plugin, so the second caller is silent
instead of printing the same context twice.
"""
import json
import os
import socket
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import obsidian_common  # noqa: E402  pylint: disable=wrong-import-position

# The four states, plus the line printed when the evidence picks none of them
# out. Named constants rather than literals at the call sites so the suite can
# assert that two states really do render differently: collapsing any two of
# these back into one word is the exact regression this file exists to stop.
VERDICT_NOT_OPEN = "NOT OPEN"
VERDICT_NO_SERVER = "NO SERVER"
VERDICT_NOT_ANSWERING = "NOT ANSWERING YET"
VERDICT_UP = "UP"
VERDICT_UNDETERMINED = "DOWN, CAUSE NOT DETERMINED"

PROBE_TIMEOUT = 2.0


def listening(port, timeout=0.4):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def probe(http_port, api_key, path="/"):
    import urllib.request
    req = urllib.request.Request(
        f"http://127.0.0.1:{http_port}{path}",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(req, timeout=PROBE_TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def served_root(http_port, api_key):
    """The vault root listing this server reports, or None if it would not say.

    Used only for the identity check - a failure here is not a bridge failure,
    so it degrades to "cannot tell" rather than downgrading the whole verdict.
    """
    try:
        body = probe(http_port, api_key, "/vault/")
    except Exception:  # pylint: disable=broad-except
        return None
    files = body.get("files") if isinstance(body, dict) else None
    return files if isinstance(files, list) else None


def emit(text):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": text,
        }
    }))


def claim(session_id):
    """True if this call is the first for session_id, across whichever
    interpreter's SessionStart entry actually fires. Best-effort: a failure to
    claim just means both flavours print the same context, which is harmless.
    """
    if not session_id:
        return True
    marker = os.path.join(tempfile.gettempdir(), f"obsidian-vault-bridge-status-{session_id}.claim")
    try:
        fd = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        return True
    except FileExistsError:
        return False
    except OSError:
        return True


def collision_sentence(name, mine):
    """Why a duplicate port is the diagnosis, in the words a reader can act on.

    Named first, ahead of every other explanation, because a collision makes
    the loser fail in three places at once (no HTTP listener, an HTTPS port
    answering someone else's key, someone else's files) and each of those
    symptoms has a plausible-looking wrong cause of its own.
    """
    parts = []
    for c in mine:
        others = sorted({claim["vault"] for claim in c["claims"]} - {name})
        who = " and ".join(others) if others else name
        parts.append(
            f"PORT COLLISION: {obsidian_common.describe_collision(c)}. Only one process "
            f"can bind :{c['port']}; the loser's Local REST API plugin then fails to start "
            f"its server AT ALL, so that vault serves nothing on either protocol and the "
            f"port that does answer is {who}'s, serving {who}'s files. Give each vault its "
            f"own ports in its data.json, then reload both (app:reload) - the plugin reads "
            f"data.json only at load."
        )
    return " ".join(parts)


def window_sentence(window):
    """The window check reported as what it looked at, not as a conclusion.

    An outage line that omits a check it could not run reads exactly like one
    where the check passed. So the sentence always says what was examined, and
    names both what could not be determined and the check that would settle
    it whenever that is the case.
    """
    parts = [f"Window check: {window['evidence']}."]
    if window["cannot"]:
        parts.append(f"NOT DETERMINED: {window['cannot']}.")
    if window["next_check"]:
        parts.append(f"To settle that: {window['next_check']}.")
    return " ".join(parts)


def unbound_line(name, vault, ports_note, collision_note, window, settings):
    """The line for a vault with nothing listening on either port.

    Three of the four states land here and they are NOT interchangeable: a
    closed window is not a fault at all, an open window with no server is a
    fault in the plugin's start-up, and an unreadable window list is neither -
    it is this script admitting it cannot tell those two apart.
    """
    flag_note = ""
    if settings["enable_insecure_server"] is False:
        # Verified on disk, and scoped to exactly what it explains: the flag
        # governs the HTTP listener only, so it is never the whole story when
        # HTTPS is silent too.
        flag_note = (f" Verified on disk: 'enableInsecureServer' is false in "
                     f"{settings['data_path']}, which accounts for the HTTP port being "
                     f"silent but NOT for the HTTPS one.")

    if window["state"] == obsidian_common.WINDOW_OPEN:
        cause = collision_note or (
            "This script did NOT determine why it failed to start. What is still open: the "
            "plugin is disabled for this vault, it threw at load, or Obsidian was launched "
            "before it was enabled - it reads its plugin list only at launch. The checks that "
            f"separate those: Settings > Community plugins for this vault, Obsidian's developer "
            f"console for a load error, and vault_ops.py diagnose --vault {name} for the on-disk "
            "half."
        )
        # The claim is quoted from the check, not restated in this function's
        # own words: if the evidence a future platform supplies ever means
        # something weaker than "a titled window names this vault", the line
        # weakens with it instead of overclaiming, which is exactly how the
        # enableInsecureServer message drifted from what had been verified.
        return (
            f"{name} ({vault}): {VERDICT_NO_SERVER} - {window['evidence']}, so Obsidian is "
            f"alive here, but nothing is bound ({ports_note}): its Local REST API server is "
            f"not. {cause}{flag_note} mcp__obsidian-{name}__* will fail; the filesystem still "
            "works."
        )

    if window["state"] == obsidian_common.WINDOW_ABSENT:
        latent = f" Separately, and NOT the cause of this: {collision_note}" if collision_note \
            else ""
        return (
            f"{name} ({vault}): {VERDICT_NOT_OPEN} - {window['evidence']}, so nothing is "
            f"expected to be listening ({ports_note}) and this is not a bridge fault to fix. "
            f"mcp__obsidian-{name}__* cannot work until the vault is open in Obsidian. A closed "
            "window is not a quit app: Obsidian stays resident in the tray with every vault "
            f"closed, so reopening the vault is what starts its server.{latent} Work from the "
            "filesystem meanwhile."
        )

    lead = f"{collision_note} " if collision_note else ""
    return (
        f"{name} ({vault}): {VERDICT_UNDETERMINED} - nothing is bound ({ports_note}). "
        f"{lead}Two states fit this evidence and this script cannot separate them: (1) the "
        f"vault is not open in Obsidian at all, which is not a fault; (2) it is open and its "
        f"Local REST API server never started, which is. {window_sentence(window)}"
        f"{flag_note} Treat mcp__obsidian-{name}__* as unavailable either way."
    ).strip()


def not_answering_line(name, vault, http_port, error, collision_note=""):
    """Bound, but no usable answer. Two causes fit, and only time tells them apart.

    Deliberately not called "broken": on a large vault the overwhelmingly
    common reason a bound port stays silent is the plugin still building its
    index after a restart, which resolves itself and must not be reported as
    something to go and fix. The exception type is what was actually observed,
    so it is quoted rather than interpreted - a timeout and an immediate reset
    do not point the same way, and the line says which one happened.

    A collision is named BEFORE either of those, because it changes what the
    silence even means: with a duplicate port, the server that accepted the
    connection need not be this vault's at all, and "wait, it is indexing" is
    then advice to wait for something that is never going to happen.
    """
    kind = type(error).__name__
    timed_out = isinstance(error, TimeoutError) or "timed out" in str(error).lower()
    if timed_out:
        weighting = (f"The probe TIMED OUT after {PROBE_TIMEOUT:g}s rather than being refused, "
                     "which is what a plugin busy indexing looks like from outside")
    else:
        weighting = (f"The probe failed immediately ({kind}: {error}) rather than timing out, "
                     "so a busy server is the less likely of the two")
    lead = (f"{collision_note} Fix that first: with a duplicate port, whatever accepted this "
            "connection need not be this vault's server at all, and neither reading below is "
            "safe until each vault has its own ports. ") if collision_note else ""
    return (
        f"{name} ({vault}): {VERDICT_NOT_ANSWERING} - 127.0.0.1:{http_port} accepts "
        f"connections, so a server IS bound, but the API returned no usable response "
        f"({kind}). {lead}Two causes fit equally and one probe cannot separate them: the plugin is "
        "still building its index after a restart - normal on a large vault, NOT a fault to "
        f"fix, and it clears on its own - or the server is wedged. {weighting}. The check that "
        f"separates them is time: re-probe in a minute (vault_ops.py diagnose --vault {name}); "
        "still silent means wedged, an answer means it was indexing. Until then treat "
        f"mcp__obsidian-{name}__* as not ready yet; the filesystem works now."
    )


def key_rejected_line(name, vault, http_port, rest_data, collision_note):
    return (
        f"{name} ({vault}): reachable on :{http_port} but the API key was REJECTED. "
        f"Either the key in {rest_data} no longer matches the MCP server config for "
        f"this vault, or the server answering :{http_port} belongs to a DIFFERENT "
        f"vault. {collision_note} Check which before re-adding the key: "
        f"vault_ops.py diagnose --vault {name}."
    ).strip()


def status_line(name, entry, collisions=(), all_paths=None, settings=None, procs=None):
    """One line for one vault.

    `procs` is obsidian_window_evidence() output, gathered once per run by
    main() and passed in. None means the window check was not run at all, and
    is reported that way - never as a vault that is closed.
    """
    vault = entry["path"]
    s = settings if settings is not None else obsidian_common.read_rest_settings(vault)
    rest_data = s["data_path"]
    mine = obsidian_common.collisions_for(collisions, name)
    collision_note = collision_sentence(name, mine) if mine else ""

    if not s["installed"]:
        where = "the plugin folder is there but has never run" if s["plugin_dir_present"] \
            else "no plugin folder either"
        return (
            f"{name} ({vault}): Local REST API is NOT INSTALLED - no {rest_data} "
            f"({where}). This is not a bridge that is down; there is no bridge. "
            f"mcp__obsidian-{name}__* cannot work until the plugin is installed and "
            "enabled for this vault (/obsidian-vault:init, or vault_ops.py "
            "enable-plugin). Work from the filesystem."
        )

    http_port, https_port = obsidian_common.resolve_ports(vault, entry.get("port"), s)
    if http_port is None and https_port is None:
        return (
            f"{name} ({vault}): {rest_data} names no usable port (checked 'insecurePort' "
            f"for HTTP and 'port' for HTTPS). Nothing can be probed. {collision_note}"
        ).strip()

    http_up = listening(http_port) if http_port else False
    https_up = listening(https_port) if https_port else False
    ports_note = (f"HTTP :{http_port if http_port else '-'} / "
                  f"HTTPS :{https_port if https_port else '-'}")

    if not http_up and not https_up:
        window = obsidian_common.vault_window_state(vault, procs, all_paths or {})
        return unbound_line(name, vault, ports_note, collision_note, window, s)

    if not http_up:
        head = (f"{name} ({vault}): HTTPS :{https_port} is up but HTTP :{http_port} is DOWN. "
                f"The MCP server for this vault is registered against "
                f"http://127.0.0.1:{http_port}/mcp and will fail to connect. Do not repoint "
                f"it at :{https_port} - Claude Code's Node client rejects the self-signed "
                "certificate.")
        if collision_note:
            return f"{head} {collision_note}"
        if s["enable_insecure_server"] is False:
            return (
                f"{head} 'enableInsecureServer' is false in {rest_data} - set it to true "
                "and reload Obsidian (command app:reload)."
            )
        return (
            f"{head} 'enableInsecureServer' is already true in {rest_data}, so that is NOT "
            "the cause - do not go re-tick it. The running plugin read data.json at load "
            "and has not seen it since: reload Obsidian (app:reload) so the live instance "
            "matches disk, and check no other vault claims this port."
        )

    try:
        info = probe(http_port, s["api_key"] or "")
    except Exception as e:  # pylint: disable=broad-except
        # A 401 is the server ANSWERING, not the silence of state 3, and
        # folding the two together would report a wrong key as "still
        # indexing" and have the reader wait for a state that never arrives.
        if getattr(e, "code", None) == 401:
            return key_rejected_line(name, vault, http_port, rest_data, collision_note)
        return not_answering_line(name, vault, http_port, e, collision_note)

    if not info.get("authenticated"):
        return key_rejected_line(name, vault, http_port, rest_data, collision_note)

    identity = obsidian_common.identity_check(vault, served_root(http_port, s["api_key"] or ""),
                                              all_paths or {})
    if identity["verdict"] == "mismatch":
        served = identity["served_vault"]
        who = f"vault '{served}'" if served else "some other vault"
        return (
            f"{name} ({vault}): WRONG VAULT on :{http_port} - the server answers and "
            f"authenticates, but it is serving {who}, not this one ({identity['detail']}). "
            f"Every mcp__obsidian-{name}__* call would read and write the wrong vault. "
            f"{collision_note}"
        ).strip()

    ver = info.get("versions") or {}
    layout_note = f" Layout: {entry['layout']}." if entry.get("layout") else ""
    line = (
        f"{name} ({vault}): {VERDICT_UP} and authenticated (Obsidian {ver.get('obsidian', '?')}, "
        f"Local REST API {ver.get('self', '?')}) on http://127.0.0.1:{http_port}. "
        f"mcp__obsidian-{name}__* is live.{layout_note}"
    )
    if collision_note:
        # This vault won the bind. Say so anyway: the loser is a different
        # vault's line, and on a machine where the loser was never configured
        # there is no other line for it to appear on.
        return f"{line} {collision_note}"
    return line


def main():
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        payload = {}
    if not claim(payload.get("session_id")):
        return 0

    vaults = obsidian_common.list_vaults()
    if not vaults:
        return 0

    # Collisions are looked for across EVERY vault on the machine, not just the
    # configured ones: a vault nobody configured still binds the port it
    # declares, and that is exactly how a configured vault ends up dark for a
    # reason none of its own settings can explain.
    all_vaults = obsidian_common.discover_vaults()
    settings = obsidian_common.collect_rest_settings(all_vaults)
    collisions = obsidian_common.find_port_collisions(all_vaults, settings)
    all_paths = {n: e["path"] for n, e in all_vaults.items()}

    # Gathered once for the whole run, not once per vault: on Windows it walks
    # every top-level window, and on macOS it spawns ps. Both are cheap once
    # and wasteful per vault.
    procs = obsidian_common.obsidian_window_evidence()

    default_name = obsidian_common.default_vault_name()
    lines = [status_line(name, entry, collisions, all_paths, settings.get(name), procs)
             for name, entry in vaults.items()]
    prefer_note = (
        "\nOn any vault past roughly 50k notes, prefer plain filesystem Read/Grep over "
        "Omnisearch/backlink MCP calls - both get slow at that scale. Use MCP for what "
        "only the running app can do."
        if any((entry.get("layout") or "").strip() for entry in vaults.values())
        else ""
    )
    emit(
        f"Obsidian vault bridge ({len(vaults)} configured):\n{chr(10).join(lines)}\n"
        f"Default vault: {default_name}. Read each vault's own CLAUDE.md before writing a "
        f"note - it is the source of truth for its frontmatter contract and tag "
        f"vocabulary.{prefer_note}"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        # This hook never blocks a session either way, but silently eating
        # every exception here (as this used to) hid a real bug: a non-integer
        # config port reaching the port arithmetic this file used to do raised
        # TypeError and vanished without a trace. Say what broke, then still
        # exit 0 - a broken bridge probe is not a reason to refuse the turn.
        print(f"obsidian-vault bridge-status.py: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(0)
