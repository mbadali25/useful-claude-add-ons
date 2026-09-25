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
import hashlib
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


def transcript_key(trigger, transcript):
    """Stable id for a capture that has a transcript but no usable session id.

    Two invocations of the SAME event (the .sh and .ps1 twins firing for one
    hook on a Windows host that has both bash and pwsh on PATH, or a hook
    that simply fires twice) carry the same trigger and transcript path, so
    this hashes to the same key both times - unlike sid="?", which never
    matched itself and so never deduped at all.
    """
    digest = hashlib.sha256(f"{trigger}\x00{transcript}".encode("utf-8", "surrogateescape"))
    return digest.hexdigest()[:16]


def already_queued(vault, sid, key=None):
    """True when this session id - or, with no usable session id, this
    trigger+transcript key - is already in this host's queue or the legacy
    queue."""
    if key is not None:
        needle = f"key={key}"
    elif sid == "?":
        # No session id and nothing to dedupe on either: main() refuses to
        # queue this case at all (see there), so this branch is never
        # reached with key=None and sid="?" today - kept explicit rather
        # than falling through to a needle that could never match itself.
        return False
    else:
        needle = f"session={sid} "
    for path in (inbox_path(vault), legacy_inbox_path(vault)):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if key is not None:
            if needle in text:
                return True
        elif needle in text or text.rstrip().endswith(f"session={sid}"):
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
        # `or "?"` rather than a plain `.get(key, "?")` default: a payload
        # that carries the key with an explicit null or empty string is just
        # as unusable as one that omits it, and both must count as "?" below.
        sid = data.get("session_id") or "?"
        cwd = data.get("cwd") or "?"
        transcript = data.get("transcript_path") or "?"

        usable_sid = sid if sid != "?" else None
        usable_transcript = transcript if transcript != "?" else None

        if usable_sid is None and usable_transcript is None:
            # Nothing to distil and nothing to dedupe on: queuing this would
            # add one unusable line per trigger per flavour (bash, PowerShell)
            # that the gardener can never resolve to anything and that can
            # never be told apart from the next one either - the defect this
            # fix closes. Say why on the channel this hook already uses for
            # every other skipped capture, and stop.
            print(f"obsidian-vault vault-capture.py: not captured: no usable session id and "
                  f"no transcript path in the hook payload (trigger={trigger}) - nothing to "
                  f"distil and nothing to dedupe on", file=sys.stderr)
            return

        key = None
        if usable_sid is None:
            # A transcript exists but the session id does not: dedupe on
            # trigger+transcript instead of on sid="?", which never matched
            # itself. This is what stops the .sh/.ps1 twins (or a hook that
            # simply fires twice for one event) from both queuing the same
            # transcript.
            key = transcript_key(trigger, usable_transcript)

        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        line = f"- [ ] {ts} | {trigger} | session={sid} | cwd={cwd} | transcript={transcript}"
        if key is not None:
            line += f" | key={key}"
        line += "\n"
        inbox = inbox_path(vault)
        inbox.parent.mkdir(parents=True, exist_ok=True)
        if already_queued(vault, sid, key=key):
            return  # one queue entry per session (or per transcript+trigger)
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
