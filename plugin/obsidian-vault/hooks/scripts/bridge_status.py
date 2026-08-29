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
import obsidian_common  # noqa: E402  pylint: disable=wrong-import-position


def listening(port, timeout=0.4):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def probe(http_port, api_key):
    import urllib.request
    req = urllib.request.Request(
        f"http://127.0.0.1:{http_port}/",
        headers={"Authorization": f"Bearer {api_key}"},
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
    marker = os.path.join(tempfile.gettempdir(), f"obsidian-vault-bridge-status-{session_id}.claim")
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
            f"{name} ({vault}): DOWN - nothing listening on 127.0.0.1:{http_port} or "
            f":{https_port}. mcp__obsidian-{name}__* will fail. Obsidian either is not "
            "running this vault, or was launched before the plugin was enabled - it needs "
            "a full quit from the tray icon, not just a window close, then a relaunch. "
            "Work from the filesystem instead."
        )

    rest_data = obsidian_common.rest_api_data_path(vault)
    if not http_up:
        return (
            f"{name} ({vault}): HTTPS :{https_port} is up but HTTP :{http_port} is DOWN. "
            f"The MCP server for this vault is normally registered against "
            f"http://127.0.0.1:{http_port}/mcp and will fail to connect. Re-enable "
            f"'enableInsecureServer' in {rest_data} and reload Obsidian (command "
            f"app:reload). Do not repoint the MCP server at :{https_port} - Claude Code's "
            "Node client rejects the self-signed certificate."
        )

    try:
        with open(rest_data, "r", encoding="utf-8") as fh:
            key = json.load(fh).get("apiKey", "")
        info = probe(http_port, key)
    except Exception as e:
        return (
            f"{name} ({vault}): port 127.0.0.1:{http_port} is open but the API did not "
            f"answer ({type(e).__name__}). Treat mcp__obsidian-{name}__* as unavailable "
            "until proven otherwise; the filesystem still works."
        )

    if not info.get("authenticated"):
        return (
            f"{name} ({vault}): reachable on :{http_port} but the API key was REJECTED. "
            f"The key in {rest_data} no longer matches the MCP server config for this "
            f"vault. Re-run: claude mcp remove --scope user obsidian-{name}, then re-add "
            "with the current apiKey, or run /obsidian-vault:doctor."
        )

    ver = info.get("versions") or {}
    layout_note = f" Layout: {entry['layout']}." if entry.get("layout") else ""
    return (
        f"{name} ({vault}): UP and authenticated (Obsidian {ver.get('obsidian', '?')}, "
        f"Local REST API {ver.get('self', '?')}) on http://127.0.0.1:{http_port}. "
        f"mcp__obsidian-{name}__* is live.{layout_note}"
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
        # every exception here (as this used to) hid a real bug: a
        # non-integer config port reaching `http_port + 1` above raised
        # TypeError and vanished without a trace. Say what broke, then still
        # exit 0 - a broken bridge probe is not a reason to refuse the turn.
        print(f"obsidian-vault bridge-status.py: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(0)
