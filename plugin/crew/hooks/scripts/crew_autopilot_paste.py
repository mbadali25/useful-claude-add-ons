"""Paste-safe removal text for a file autopilot will not touch itself, and the
focus marker's lock (T-0020).

Moved unchanged out of `crew_autopilot.py` to keep it under pylint's 3400-line
cap when G6a met release/1.2.0. `crew_autopilot` keeps its names: `_focus_lock`
is a wrapper there that reads `crew_autopilot.FOCUS_LOCK_WAIT` at call time, so
a test patching that constant still bounds the wait, and the other names are
re-exported for its callers.
"""

from __future__ import annotations

import json
import os
import re
import shlex

# PowerShell reads U+2018..U+201B as single quotes too.
PS_QUOTES = ("'", "\u2018", "\u2019", "\u201a", "\u201b")
# C0, DEL and C1 controls (a terminal acts on C1 too), the PowerShell quotes,
# and the bidi embedding/override/isolate controls U+202A..U+202E and
# U+2066..U+2069 (they reorder what a person reads): the JSON form instead.
UNSAFE_PATH = re.compile(r"[\x00-\x1f\x7f-\x9f\u2018-\u201b\u202a-\u202e\u2066-\u2069]|\s{2,}")


def posix_quoted(path):
    return "'" + path.replace("'", "'\\''") + "'"


def ps_quoted(path):
    for mark in PS_QUOTES:
        path = path.replace(mark, mark * 2)
    return "'" + path + "'"


def paste_safe(path):
    """Whether `path` survives into a printed command unchanged: no control
    character (C0, DEL or C1), no bidi control, no run of whitespace
    (`crew_autopilot._one_line` would collapse it), no quote PowerShell also
    reads, and the POSIX command parses back to exactly `rm -- <path>`."""
    if UNSAFE_PATH.search(path):
        return False
    rm_part = f"rm -- {posix_quoted(path)}"
    try:
        return shlex.split(rm_part) == ["rm", "--", path] and " ".join(rm_part.split()) == rm_part
    except ValueError:
        return False


def remove_by_hand(path, effect):
    """`effect`, then paste-ready removal commands for `path` (POSIX and
    PowerShell) when it is paste-safe, else the path as JSON and "remove
    this file by hand", with no command that could name another file."""
    if not paste_safe(path):
        # JSON escapes control characters; a run of spaces is escaped too, so
        # `_one_line`'s collapse cannot change the path it names.
        shown = re.sub(r" {2,}", lambda run: "\\u0020" * len(run.group()), json.dumps(path))
        return f"{effect}: remove this file by hand: {shown}"
    return (f"{effect}: rm -- {posix_quoted(path)} (POSIX shell) or "
            f"Remove-Item -LiteralPath {ps_quoted(path)} (PowerShell)")


def focus_remedy(path):
    """The way out of an unknown marker, naming its exact path: `focus off`
    refuses to touch a file it cannot read, so the human removes it."""
    return remove_by_hand(path, "removing it drops EVERY worktree's focus, not only this one's")


class FocusLockError(Exception):
    """The marker's lock could not be taken; nothing was written."""


class FocusLock:  # pylint: disable=too-few-public-methods
    """`<marker>.lock`, crew_config_files.Lock's exclusive create with a
    bounded wait, around every read-modify-write of the marker: two worktrees
    running `focus` at once would otherwise both read the old mapping and the
    later write would drop the other's entry while both report success. A
    lock that cannot be taken raises FocusLockError; nothing writes
    unlocked."""

    def __init__(self, path, wait):
        import crew_config_files  # pylint: disable=import-outside-toplevel
        self.path, self.files = path, crew_config_files
        self.lock = crew_config_files.Lock(path, wait)

    def __enter__(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            self.lock.__enter__()
        except (self.files.Busy, OSError) as exc:
            raise FocusLockError(
                f"refused: the focus marker's lock {self.path}.lock could not be taken "
                f"({exc}); nothing written. If no focus command is running, a process "
                "died holding it; " + remove_by_hand(
                    self.path + ".lock", "removing the lock releases it")) from exc
        return self

    def __exit__(self, *exc):
        self.lock.__exit__(*exc)
