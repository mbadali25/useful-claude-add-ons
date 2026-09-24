"""One emission per event from hooks whose only effect is output or a write.

hooks.json registers every hook twice, a bash `command` and a
`shell: "powershell"` twin. Each .ps1 stands down off Windows, but no .sh
stands down on Windows -- and must not: CLAUDE.md records the release where
an OS-based stand-down left a guard blocking nothing. So on Windows both
flavours can run for one event. For a blocking hook that is only a cost (two
identical verdicts). For a hook that EMITS -- a chat ping, a handoff
skeleton, a transcript copy -- it is a visible duplicate.

Blocking hooks (scope-guard, completion-audit, cloud-guard, role-write-guard,
approval-hook, verify-gate) take NO claim and keep running in both flavours:
a claim would let whichever flavour lost its python decide alone. The cost of
that, measured 2026-09-23 on Linux with pwsh (OS=Windows_NT), median of 5: the
.ps1 run adds ~0.5-0.65s per hook (sh ~0.08s), ~1.2s per Edit/Bash PreToolUse
when two guards match if the harness runs them serially; the burn-in measured
pwsh at ~2.2x python per invocation on Windows itself.

This is the claim those hooks take, the general form of crew_context.py's
`claim`: both flavours hash the same payload bytes, and O_CREAT|O_EXCL on a
marker named by that hash decides which one emits. No knowledge of the
platform, so it cannot stand the wrong flavour down.

Why not hook_once.py: its key is (hook, session) and never expires inside a
session, which is right for SessionStart and wrong for Notification and
PreCompact, both of which fire many times per session -- a second ping would
be suppressed for the rest of the session. Here the key also carries the
payload digest, and a claim stands for WINDOW seconds: long enough for the
slower flavour (pwsh starts in ~0.3-0.7s on Windows) to find it, short enough
that the same notification text an hour later is a new event.

Usage:  <python> event_claim.py <hook-name> <root>   (hook payload on stdin)
Exit 0   emit.
Exit 10  the other flavour already emitted this event -- exit quietly.
Anything else (a crash, a missing interpreter) means "could not decide", and
callers emit: a duplicate is the safe failure, a suppressed handoff is not.
An empty payload is not a hook invocation (a command calling notify.sh by
hand) and always emits.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time

LOST = 10
WINDOW = 60
_STALE_SECONDS = 24 * 60 * 60
_READ_SECONDS = 5


def claims_dir(root):
    """`<git-common-dir>/crew/event-claims`, beside crew_context.py's
    context-claims, so a worktree and its main checkout share one set and
    nothing lands in the working tree. Outside git, `.crew/event-claims`."""
    try:
        done = subprocess.run(["git", "-C", root, "rev-parse", "--git-common-dir"],
                              capture_output=True, text=True, timeout=10, check=False)
        common = done.stdout.strip() if done.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        common = ""
    if common:
        base = common if os.path.isabs(common) else os.path.join(root, common)
        return os.path.join(base, "crew", "event-claims")
    return os.path.join(root, ".crew", "event-claims")


def normalise(raw):
    """The bytes both flavours agree on. bash's `$(cat)` drops trailing
    newlines and a PowerShell read can keep a BOM, so neither survives into
    the key."""
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    return raw.strip()


def _session(raw):
    try:
        data = json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        return "nosession"
    session = data.get("session_id") if isinstance(data, dict) else None
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(session or "nosession"))[:64]


def _prune(directory, now):
    cutoff = now - _STALE_SECONDS
    try:
        names = os.listdir(directory)
    except OSError:
        return
    for name in names:
        path = os.path.join(directory, name)
        try:
            if os.path.getmtime(path) < cutoff:
                os.unlink(path)
        except OSError:
            pass


def _create(path):
    try:
        handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return False
    os.close(handle)
    return True


def claim(root, hook, raw, now=None):
    """True when this process emits for this event."""
    raw = normalise(raw)
    if not raw:
        return True
    now = time.time() if now is None else now
    directory = claims_dir(root)
    digest = hashlib.sha256(hook.encode("utf-8") + b"\0" + raw).hexdigest()[:32]
    path = os.path.join(directory, f"{hook}-{_session(raw)}-{digest}")
    try:
        os.makedirs(directory, exist_ok=True)
        _prune(directory, now)
        if _create(path):
            return True
        mtime = os.path.getmtime(path)
    except OSError:
        return True
    if now - mtime < WINDOW:
        return False
    # The marker is from an EARLIER identical event. Both flavours of this one
    # read the same old mtime, so they race for the same takeover name and
    # O_EXCL picks one; the winner refreshes the marker for the next event.
    try:
        if not _create(f"{path}.{int(mtime)}"):
            return False
        os.utime(path, (now, now))
    except OSError:
        return True
    return True


def _read_stdin():
    """stdin, or b"" when nothing arrives in time. A caller that leaves stdin
    open and never writes -- a terminal, a harness pipe -- must not hang the
    hook; the payload Claude Code sends is written and closed at once."""
    box = []
    reader = threading.Thread(target=lambda: box.append(sys.stdin.buffer.read()), daemon=True)
    reader.start()
    reader.join(_READ_SECONDS)
    return box[0] if box else None


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 2:
        return 0
    raw = _read_stdin()
    if raw is None:
        sys.stdout.flush()
        os._exit(0)  # the reader thread is still blocked; do not wait on it
    return 0 if claim(os.path.abspath(args[1]), args[0], raw) else LOST


if __name__ == "__main__":
    raise SystemExit(main())
