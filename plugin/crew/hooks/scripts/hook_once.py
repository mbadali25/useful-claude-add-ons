"""Grants one caller per session the right to run a hook.

Both the .sh and .ps1 flavour of every matcher-less hook are registered, so
both fire wherever both interpreters exist. Deciding by interpreter does not
work: on Windows `bash` on PATH is usually C:\\Windows\\System32\\bash.exe, the
WSL launcher, which cannot resolve the plugin's own path -- so a .ps1 that
steps aside for "a bash" can step aside for one that then fails, leaving the
hook unrun.

A claim decides by arrival instead, which needs no knowledge of the platform.
The winner is whichever process creates the marker first; O_CREAT|O_EXCL makes
that atomic, so a tie cannot produce two winners.

Use this ONLY for events that fire once per session (SessionStart). The
marker is keyed on (hook, session) and is not cleared after a successful
claim -- only pruned after 24h -- so it is wrong for anything that can fire
more than once against the same session id. Stop is the case that bit us:
it fires once per TURN, so a claim taken on turn 1 suppresses the hook for
every later turn in that session, which for a 600-second verify gate reads
as "the work passed". For those events (Stop, Notification, PreCompact),
prefer letting both flavours run -- duplication there is a safe failure,
suppression is not.

Usage:  python3 hook_once.py <hook-name> <session-id>
Exit 0  you won the claim -- do the work.
Exit 1  someone else already has it -- exit quietly.
"""

import os
import sys
import time

# Markers older than this are from dead sessions. Generous on purpose: the cost
# of a stale marker is one skipped hook, the cost of pruning too eagerly is a
# double-fire.
_STALE_SECONDS = 24 * 60 * 60


def _prune(dirpath):
    """Drop markers from sessions that are long gone."""
    cutoff = time.time() - _STALE_SECONDS
    try:
        names = os.listdir(dirpath)
    except OSError:
        return
    for name in names:
        if not name.startswith(".hook-"):
            continue
        path = os.path.join(dirpath, name)
        try:
            if os.path.getmtime(path) < cutoff:
                os.unlink(path)
        except OSError:
            pass


def claim(root, hook, session):
    """True if this process may run `hook` for `session`.

    Returns True when there is nowhere to put a marker -- a repo with no
    .crew/ is not a crew repo, and the caller will no-op on its own. Failing
    open here keeps the decision in one place.

    A missing `session` does NOT fail open. An earlier version of this
    returned True unconditionally when `session` was falsy, on the theory
    that running twice is bad but never running is worse -- but "no scope"
    is not the same as "no guarantee". The .sh and .ps1 flavours of a hook
    both fire for the same event, and if the payload happens to carry no
    session id, failing open let both of them race a write with nothing to
    stop it -- exactly the double-fire this module exists to prevent. A
    calendar-day key is used instead: coarser than a real session id (two
    genuinely separate no-session invocations on the same day only get the
    first one), but it still lets the FIRST caller through and still runs
    again on the next day, rather than going silent forever the way a
    single persistent fallback key would.
    """
    if not session:
        session = "nosession-" + time.strftime("%Y%m%d")
    dirpath = os.path.join(root, ".crew")
    if not os.path.isdir(dirpath):
        return True
    _prune(dirpath)
    marker = os.path.join(dirpath, f".hook-{hook}-{session}")
    try:
        fd = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return False
    except OSError:
        return True
    os.close(fd)
    return True


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 2:
        return 0
    hook, session = args[0], args[1]
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    return 0 if claim(root, hook, session) else 1


if __name__ == "__main__":
    raise SystemExit(main())
