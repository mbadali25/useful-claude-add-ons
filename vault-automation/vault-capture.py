#!/usr/bin/env python3
"""Append a session-capture entry to the Obsidian vault inbox for nightly reflection.

Installed to ~/.claude/hooks/vault-capture.py by setup-vault-automation.ps1, which
also rewrites VAULT_PATH below to the chosen vault. Wired to Claude Code SessionEnd
and PreCompact hooks. Reads the hook JSON from stdin, appends one markdown task line
to inbox/pending-reflect.md. Never raises: a capture failure must not break a session.

Invoke with --selftest to validate config (vault path exists, inbox writable) without
writing a queue entry.
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
    try:
        trigger = sys.argv[1] if len(sys.argv) > 1 else "unknown"
        if trigger == "--selftest":
            # Validation only: config must point at a real vault and the inbox
            # location must be creatable. No queue entry is written.
            if not pathlib.Path(VAULT_PATH).is_dir():
                print(f"selftest FAIL: vault path missing: {VAULT_PATH}", file=sys.stderr)
                sys.exit(1)
            INBOX.parent.mkdir(parents=True, exist_ok=True)
            print("selftest OK")
            return
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
        INBOX.parent.mkdir(parents=True, exist_ok=True)
        if not INBOX.exists():
            INBOX.write_text(HEADER + "\n" + line, encoding="utf-8")
            return
        # One queue entry per session, whichever trigger fires first
        if sid != "?" and f"session={sid}" in INBOX.read_text(encoding="utf-8"):
            return
        with INBOX.open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass  # never break the session over a capture miss

if __name__ == "__main__":
    main()
