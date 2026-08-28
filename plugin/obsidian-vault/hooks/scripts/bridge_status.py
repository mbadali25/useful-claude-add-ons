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
import obsidian_common  # noqa: E402


def listening(port, timeout=0.4):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def probe(http_port, api_key):
    import urllib.request
    req = urllib.request.Request(
        "http://127.0.0.1:%d/" % http_port,
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
    marker = os.path.join(tempfile.gettempdir(), "obsidian-vault-bridge-status-%s.claim" % session_id)
    try:
        fd = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        return True
    except FileExistsError:
        return False
    except OSError:
        return True


def status_line(name, entry):
    vault, http_port = entry["path"], entry["port"]
    https_port = http_port + 1
    http_up, https_up = listening(http_port), listening(https_port)

    if not http_up and not https_up:
        return (
            "%s (%s): DOWN - nothing listening on 127.0.0.1:%d or :%d. mcp__obsidian-%s__* "
            "will fail. Obsidian either is not running this vault, or was launched before "
            "the plugin was enabled - it needs a full quit from the tray icon, not just a "
            "window close, then a relaunch. Work from the filesystem instead."
            % (name, vault, http_port, https_port, name)
        )

    rest_data = obsidian_common.rest_api_data_path(vault)
    if not http_up:
        return (
            "%s (%s): HTTPS :%d is up but HTTP :%d is DOWN. The MCP server for this vault "
            "is normally registered against http://127.0.0.1:%d/mcp and will fail to "
            "connect. Re-enable 'enableInsecureServer' in %s and reload Obsidian "
            "(command app:reload). Do not repoint the MCP server at :%d - Claude Code's "
            "Node client rejects the self-signed certificate."
            % (name, vault, https_port, http_port, http_port, rest_data, https_port)
        )

    try:
        with open(rest_data, "r", encoding="utf-8") as fh:
            key = json.load(fh).get("apiKey", "")
        info = probe(http_port, key)
    except Exception as e:
        return (
            "%s (%s): port 127.0.0.1:%d is open but the API did not answer (%s). Treat "
            "mcp__obsidian-%s__* as unavailable until proven otherwise; the filesystem "
            "still works." % (name, vault, http_port, type(e).__name__, name)
        )

    if not info.get("authenticated"):
        return (
            "%s (%s): reachable on :%d but the API key was REJECTED. The key in %s no "
            "longer matches the MCP server config for this vault. Re-run: claude mcp "
            "remove --scope user obsidian-%s, then re-add with the current apiKey, or run "
            "/obsidian-vault:doctor." % (name, vault, http_port, rest_data, name)
        )

    ver = (info.get("versions") or {})
    layout_note = " Layout: %s." % entry["layout"] if entry.get("layout") else ""
    return (
        "%s (%s): UP and authenticated (Obsidian %s, Local REST API %s) on "
        "http://127.0.0.1:%d. mcp__obsidian-%s__* is live.%s"
        % (name, vault, ver.get("obsidian", "?"), ver.get("self", "?"), http_port, name,
           layout_note)
    )


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

    default_name = obsidian_common.default_vault_name()
    lines = [status_line(name, entry) for name, entry in vaults.items()]
    prefer_note = (
        "\nOn any vault past roughly 50k notes, prefer plain filesystem Read/Grep over "
        "Omnisearch/backlink MCP calls - both get slow at that scale. Use MCP for what "
        "only the running app can do."
        if any((entry.get("layout") or "").strip() for entry in vaults.values())
        else ""
    )
    emit(
        "Obsidian vault bridge (%d configured):\n%s\n"
        "Default vault: %s. Read each vault's own CLAUDE.md before writing a note - it is "
        "the source of truth for its frontmatter contract and tag vocabulary.%s"
        % (len(vaults), "\n".join(lines), default_name, prefer_note)
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
