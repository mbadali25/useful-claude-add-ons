#!/usr/bin/env python3
"""Append a session-capture entry to the vault inbox for later gardening.

Generalized from a personal ~/.claude/hooks/vault-capture.py that had the vault
path baked in by an installer. This version resolves it via
obsidian_common.resolve_vault_path() at run time instead, so one script works
for every vault on every machine. Wired to SessionEnd and PreCompact.

Reads the hook JSON from stdin, appends one markdown task line to
inbox/pending-reflect.md. Never raises: a capture failure must not break a
session - this is a nice-to-have, not a gate.

Invoke with --selftest to validate that a vault resolves and its inbox is
writable, without writing a queue entry.
"""
import sys
import json
import datetime
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import obsidian_common  # noqa: E402

HEADER = (
    "# Pending reflection queue\n\n"
    "Appended automatically by vault_capture.py (SessionEnd/PreCompact hooks).\n"
    "The obsidian-vault:gardener agent processes unchecked entries and checks them off.\n"
)


def inbox_path(vault):
    return pathlib.Path(vault) / "inbox" / "pending-reflect.md"


def main():
    trigger = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    vault = obsidian_common.resolve_vault_path()

    if trigger == "--selftest":
        if not vault:
            print("selftest FAIL: no vault resolved (env, config, and Obsidian's own "
                  "registry all came up empty)", file=sys.stderr)
            sys.exit(1)
        inbox = inbox_path(vault)
        inbox.parent.mkdir(parents=True, exist_ok=True)
        try:
            if not inbox.exists():
                inbox.write_text(HEADER, encoding="utf-8")
            else:
                with inbox.open("a", encoding="utf-8"):
                    pass
        except Exception as e:
            print(f"selftest FAIL: inbox not writable: {e}", file=sys.stderr)
            sys.exit(1)
        print(f"selftest OK: vault={vault}")
        return

    if not vault:
        return  # nothing configured yet; stay silent rather than guess a path

    try:
        try:
            data = json.loads(sys.stdin.read() or "{}")
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        sid = data.get("session_id", "?")
        cwd = data.get("cwd", "?")
        transcript = data.get("transcript_path", "?")
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        line = f"- [ ] {ts} | {trigger} | session={sid} | cwd={cwd} | transcript={transcript}\n"
        inbox = inbox_path(vault)
        inbox.parent.mkdir(parents=True, exist_ok=True)
        if not inbox.exists():
            inbox.write_text(HEADER + "\n" + line, encoding="utf-8")
            return
        if sid != "?" and f"session={sid}" in inbox.read_text(encoding="utf-8"):
            return  # one queue entry per session, whichever trigger fires first
        with inbox.open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception as e:
        # Never break the session over a capture miss - but say what broke
        # instead of eating it silently, or a permissions/disk problem here
        # goes unnoticed until the inbox turns out to have been empty for
        # weeks.
        print("obsidian-vault vault-capture.py: %s: %s" % (type(e).__name__, e), file=sys.stderr)


if __name__ == "__main__":
    main()
