"""Stop-time completion scope audit, and `/crew:done`'s scope check.

crew 1.0, lane T3 (docs/review/04-redesign.md, Hooks table: "diffs the whole
tree against the scope base, catching shell-made writes too, and refuses
`done` on out-of-scope paths").

The edit guard (`scope_guard.py`) sees only Write/Edit/MultiEdit/NotebookEdit.
A `sed -i`, a redirect, a formatter or a `git mv` never reaches it. This audit
reads the result instead of the tool call: every path that differs from the
ticket's scope base (`scope_base.resolve` -- the commit the ticket started
from, falling back to MORE, never less) across committed, staged, unstaged
and untracked changes. The list comes from `review_patch.compute`, the same
temporary-index bundle the reviewer reads, so renames arrive with both ends
and BOTH must be in scope: a rename moves a file out of one path as much as
into another. The user's index is never touched.

What it cannot see, stated rather than implied: files git ignores (`.crew/*`
among them) and `.work/`, which the bundle excludes on purpose.

A path passes when it is inside the active ticket's `spec.md ## Touch`. When
the ticket's approval is not current (`crew_ticket.status` stale or none),
Touch itself is unapproved, so every changed path fails: an edited spec cannot
widen what the audit accepts until the user approves it again.

## As a Stop hook

stdin is the Stop payload. `stop_hook_active` true -> exit 0, silent: the
audit blocks a turn once and never re-blocks the continuation it caused.
`scope.mode` off, or no active ticket -> exit 0, silent. Pass -> exit 0 and
no output. Fail under `block` -> exit 2 and at most six lines on stderr; under
`report` -> exit 0 and one `systemMessage`. An audit that could not run (git
failed, no base) is a failure, never a pass.

## As `/crew:done`'s check

`completion_audit.py --check --ticket <id> [--root <dir>]` runs the same audit
whatever `scope.mode` says, prints the verdict, and exits 0 only on a pass.
"""
import argparse
import json
import os
import sys

import crew_ticket
import review_patch
import scope_base

MAX_LINES = 6


def changed_paths(top, base):
    """Every path the tree changed since `base`, both ends of a rename."""
    manifest, _patch, _parts = review_patch.compute(top, base)
    paths = []
    for entry in manifest.get("entries") or []:
        paths.append(entry["path"])
        if entry.get("status") == "R" and entry.get("old_path") != entry["path"]:
            paths.append(entry["old_path"])
    return sorted(set(paths))


def audit(root, ticket):
    """(ok, lines). `lines` explains a failure; empty on a pass."""
    top = crew_ticket.toplevel(root)
    if not top:
        return False, [f"completion audit: {root} is not a git repository; cannot audit"]
    base, source, reason = scope_base.resolve(top, ticket)
    if not base:
        return False, [f"completion audit: no scope base for {ticket} ({reason})"]
    try:
        paths = changed_paths(top, base)
    except RuntimeError as exc:
        return False, [f"completion audit: could not diff the tree: {exc}"]
    if not paths:
        return True, []
    approval = crew_ticket.status(top, ticket)
    note = "" if source == scope_base.RECORDED else " (base is a fallback: shows MORE)"
    if approval["status"] != "approved":
        return False, [f"COMPLETION AUDIT: {ticket}'s Touch is not approved "
                       f"({approval['why']}), so no change can be judged in scope.",
                       f"  Changed since {base[:12]}{note}: {' '.join(paths[:8])}"
                       + (" ..." if len(paths) > 8 else ""),
                       f"  Ask the user to run `crew_ticket.py approve --ticket {ticket}`."]
    touch = crew_ticket.touch_for(top, ticket)
    outside = [p for p in paths if not crew_ticket.in_touch(p, touch)]
    if not outside:
        return True, []
    shown = " ".join(outside[:8]) + (f" (+{len(outside) - 8} more)" if len(outside) > 8 else "")
    return False, [f"COMPLETION AUDIT: {len(outside)} changed path(s) outside {ticket}'s "
                   f"spec ## Touch{note}:",
                   f"  {shown}",
                   "  Revert them, or amend spec.md ## Touch and have the user run",
                   f"  `crew_ticket.py approve --ticket {ticket}`. Shell-made writes count."]


def _payload():
    try:
        raw = sys.stdin.buffer.read()
    except (OSError, ValueError):
        return {}
    if raw[:3] == b"\xef\xbb\xbf":
        raw = raw[3:]
    try:
        data = json.loads(raw.decode("utf-8")) if raw.strip() else {}
    except (UnicodeDecodeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def stop_hook(data):
    if data.get("stop_hook_active") is True:
        return 0
    root = data.get("cwd") if isinstance(data.get("cwd"), str) else None
    root = root or os.environ.get("CLAUDE_PROJECT_DIR") or "."
    top = crew_ticket.toplevel(root)
    if not top:
        return 0
    configured, _why = crew_ticket.configured_mode(top)
    if configured == "off":
        return 0
    ticket, _source = crew_ticket.active_ticket(root)
    if not ticket:
        return 0
    mode, why = crew_ticket.effective_mode(root, ticket)
    try:
        ok, lines = audit(root, ticket)
    except Exception as exc:  # pylint: disable=broad-except
        ok, lines = False, [f"completion audit: failed ({type(exc).__name__}: {exc}); "
                            "nothing was audited"]
    if ok:
        return 0
    if mode == "block":
        sys.stderr.write("".join(line + "\n" for line in lines[:MAX_LINES]))
        return 2
    sys.stdout.write(json.dumps({"systemMessage": "completion audit (report, would block): "
                                 + " ".join(l.strip() for l in lines[:2]) + f" ({why})"})
                     + "\n")
    return 0


def main(argv):
    if not argv:
        return stop_hook(_payload())
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", required=True)
    parser.add_argument("--ticket", required=True)
    parser.add_argument("--root", default=".")
    args = parser.parse_args(argv)
    try:
        crew_ticket.check_ticket(args.ticket)
        ok, lines = audit(os.path.abspath(args.root), args.ticket)
    except crew_ticket.TicketError as exc:
        ok, lines = False, [f"completion audit: {exc}"]
    if ok:
        print(f"completion audit: every change is inside {args.ticket}'s spec ## Touch")
        return 0
    print("\n".join(lines[:MAX_LINES]))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
