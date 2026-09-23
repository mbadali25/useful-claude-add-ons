#!/usr/bin/env python3
"""Append a session-capture entry to the vault inbox for later gardening.

Generalized from a personal ~/.claude/hooks/vault-capture.py that had the vault
path baked in by an installer. This version resolves it via
obsidian_common.writer_vault() at run time instead - the role-primary vault
and nothing else - so one script works for every vault on every machine. Wired to SessionEnd and PreCompact.

Reads the hook JSON from stdin, appends one markdown task line to
inbox/pending-reflect.<host>.md - one queue file PER HOST, so two machines
syncing the same vault never append to the same file. The legacy single queue,
inbox/pending-reflect.md, is no longer written here; it is still read (for
de-duplication here, and as a queue by the gardener) so a backlog captured by
an older version of this plugin is drained rather than stranded. This script
is the only capture owner. Never raises: a capture failure must not break a
session - this is a nice-to-have, not a gate.

Invoke with --selftest to validate that a vault resolves and its inbox is
writable, without writing a queue entry.
"""
import sys
import json
import datetime
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import obsidian_common  # noqa: E402  pylint: disable=wrong-import-position

HEADER = (
    "# Pending reflection queue\n\n"
    "Appended automatically by vault_capture.py (SessionEnd/PreCompact hooks).\n"
    "The obsidian-vault:gardener agent processes unchecked entries and checks them off.\n"
)


def legacy_inbox_path(vault):
    return pathlib.Path(vault) / "inbox" / "pending-reflect.md"


def inbox_path(vault):
    return pathlib.Path(vault) / "inbox" / f"pending-reflect.{obsidian_common.host_id()}.md"


def already_queued(vault, sid):
    """True when this session id is in this host's queue or the legacy queue."""
    if sid == "?":
        return False
    needle = f"session={sid} "
    for path in (inbox_path(vault), legacy_inbox_path(vault)):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if needle in text or text.rstrip().endswith(f"session={sid}"):
            return True
    return False


def main():
    trigger = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    # The primary vault only - never a recall/ignore vault standing in for an
    # unmounted primary (obsidian_common.writer_vault explains why).
    _, vault, problem = obsidian_common.writer_vault()

    if trigger == "--selftest":
        if not vault:
            print("selftest FAIL: " + (problem or "no vault resolved (env, config, and "
                                       "Obsidian's own registry all came up empty)"),
                  file=sys.stderr)
            sys.exit(1)
        inbox = inbox_path(vault)
        inbox.parent.mkdir(parents=True, exist_ok=True)
        try:
            if not inbox.exists():
                inbox.write_text(HEADER, encoding="utf-8", newline="\n")
            else:
                with inbox.open("a", encoding="utf-8"):
                    pass
        except Exception as e:
            print(f"selftest FAIL: inbox not writable: {e}", file=sys.stderr)
            sys.exit(1)
        print(f"selftest OK: vault={vault}")
        return

    if not vault:
        if problem:
            # Configured but unavailable: say so on stderr and still exit 0 -
            # a capture miss must not break the session, and must not be
            # silent either.
            print(f"obsidian-vault vault-capture.py: not captured: {problem}", file=sys.stderr)
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
        if already_queued(vault, sid):
            return  # one queue entry per session, whichever trigger fires first
        if not inbox.exists():
            inbox.write_text(HEADER + "\n" + line, encoding="utf-8", newline="\n")
            return
        with inbox.open("a", encoding="utf-8", newline="\n") as f:
            f.write(line)
    except Exception as e:
        # Never break the session over a capture miss - but say what broke
        # instead of eating it silently, or a permissions/disk problem here
        # goes unnoticed until the inbox turns out to have been empty for
        # weeks.
        print(f"obsidian-vault vault-capture.py: {type(e).__name__}: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
