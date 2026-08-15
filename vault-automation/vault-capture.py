#!/usr/bin/env python3
"""Append a session-capture entry to the Obsidian vault inbox for nightly reflection.

Installed to ~/.claude/hooks/vault-capture.py by setup-vault-automation.ps1, which
also rewrites VAULT_PATH below to the chosen vault. Wired to Claude Code SessionEnd
and PreCompact hooks. Reads the hook JSON from stdin, appends one markdown task line
to inbox/pending-reflect.md. Never raises: a capture failure must not break a session.
"""
import sys, json, datetime, pathlib

VAULT_PATH = r"__VAULT_PATH__"  # rewritten by the installer
INBOX = pathlib.Path(VAULT_PATH) / "inbox" / "pending-reflect.md"
HEADER = (
    "# Pending reflection queue\n\n"
    "Appended automatically by vault-capture.py (SessionEnd/PreCompact hooks).\n"
    "The nightly vault gardener processes unchecked entries and checks them off.\n"
)

def main() -> None:
    trigger = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except Exception:
        data = {}
    sid = data.get("session_id", "?")
    cwd = data.get("cwd", "?")
    transcript = data.get("transcript_path", "?")
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    line = f"- [ ] {ts} | {trigger} | session={sid} | cwd={cwd} | transcript={transcript}\n"
    try:
        INBOX.parent.mkdir(parents=True, exist_ok=True)
        if not INBOX.exists():
            INBOX.write_text(HEADER + "\n" + line, encoding="utf-8")
        else:
            existing = INBOX.read_text(encoding="utf-8")
            # One entry per session: repeated compactions don't re-queue
            if f"session={sid}" in existing and trigger == "pre-compact":
                return
            with INBOX.open("a", encoding="utf-8") as f:
                f.write(line)
    except Exception:
        pass  # never break the session over a capture miss

if __name__ == "__main__":
    main()
