#!/usr/bin/env python3
"""SessionStart probe for the Obsidian Local REST API bridge.

Generalized from a personal ~/.claude/hooks/obsidian-bridge-status.py: the vault
path now comes from obsidian_common.resolve_vault_path() instead of being
hardcoded, so the same script works on any machine and any vault.

The failure this exists to prevent: the MCP client can look healthy while
Obsidian is not actually listening, because Obsidian reads its plugin list only
at launch and closing the window merely minimizes it to the tray. Claude then
assumes mcp__obsidian__* works and stalls when it does not.

This states the ground truth up front. It never blocks a session - SessionStart
hooks cannot block, and even if they could, "the bridge is down" is information,
not a reason to refuse the turn.

SessionStart fires once per interpreter that is actually present on the
machine, which on Windows is normally both bash (Git Bash) and PowerShell. Only
one is meant to speak: a claim file per session id, mirroring the pattern
platform-sync.py uses in the crew plugin, so the second caller is silent
instead of printing the same context twice.
"""
import json
import os
import socket
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import obsidian_common  # noqa: E402

HTTP_PORT, HTTPS_PORT = 27123, 27124


def listening(port, timeout=0.4):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def probe(api_key):
    import urllib.request
    req = urllib.request.Request(
        "http://127.0.0.1:%d/" % HTTP_PORT,
        headers={"Authorization": "Bearer %s" % api_key},
    )
    with urllib.request.urlopen(req, timeout=2.0) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


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
    marker = os.path.join(tempfile.gettempdir(), "obsidian-bridge-status-%s.claim" % session_id)
    try:
        fd = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        return True
    except FileExistsError:
        return False
    except OSError:
        return True


def main():
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        payload = {}
    if not claim(payload.get("session_id")):
        return 0

    vault = obsidian_common.resolve_vault_path()
    if not vault:
        return 0

    http_up, https_up = listening(HTTP_PORT), listening(HTTPS_PORT)

    if not http_up and not https_up:
        emit(
            "Obsidian bridge: DOWN (nothing listening on 127.0.0.1:%d or :%d).\n"
            "The mcp__obsidian__* tools and the REST API will fail. Obsidian is either not "
            "running or was launched before the plugin was enabled - it needs a full quit from "
            "the tray icon, not just a window close, then a relaunch.\n"
            "Work from the filesystem at %s instead, and say the bridge is down rather than "
            "retrying." % (HTTP_PORT, HTTPS_PORT, vault)
        )
        return 0

    rest_data = obsidian_common.rest_api_data_path(vault)
    if not http_up:
        emit(
            "Obsidian bridge: HTTPS :%d is up but HTTP :%d is DOWN. The MCP server 'obsidian' "
            "is normally registered against http://127.0.0.1:%d/mcp and will fail to connect. "
            "Re-enable 'enableInsecureServer' in %s and reload Obsidian (command app:reload). Do "
            "not repoint the MCP server at :%d - Claude Code's Node client rejects the "
            "self-signed certificate with DEPTH_ZERO_SELF_SIGNED_CERT."
            % (HTTPS_PORT, HTTP_PORT, HTTP_PORT, rest_data, HTTPS_PORT)
        )
        return 0

    try:
        with open(rest_data, "r", encoding="utf-8") as fh:
            key = json.load(fh).get("apiKey", "")
        info = probe(key)
    except Exception as e:
        emit(
            "Obsidian bridge: port 127.0.0.1:%d is open but the API did not answer (%s). "
            "Treat mcp__obsidian__* as unavailable until proven otherwise; the filesystem at "
            "%s still works." % (HTTP_PORT, type(e).__name__, vault)
        )
        return 0

    if not info.get("authenticated"):
        emit(
            "Obsidian bridge: reachable on :%d but the API key was REJECTED. The key in %s no "
            "longer matches the one stored in the 'obsidian' MCP server config. Re-run: "
            "claude mcp remove --scope user obsidian, then re-add with the current apiKey, or "
            "run /obsidian:doctor." % (HTTP_PORT, rest_data)
        )
        return 0

    ver = (info.get("versions") or {})
    emit(
        "Obsidian bridge: UP and authenticated (Obsidian %s, Local REST API %s) on "
        "http://127.0.0.1:%d. The mcp__obsidian__* tools are live.\n"
        "Vault: %s. Prefer Read/Write/Edit/Grep on the filesystem for note CRUD and search; "
        "use MCP for what only the running app can do - command_execute, search_query "
        "(JsonLogic over frontmatter), vault_get_document_map, tag_list, and vault_read when "
        "you need its backlinks/unresolvedLinks. Read the vault's own CLAUDE.md before writing "
        "a note - it is the source of truth for its frontmatter contract and tag vocabulary."
        % (ver.get("obsidian", "?"), ver.get("self", "?"), HTTP_PORT, vault)
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
