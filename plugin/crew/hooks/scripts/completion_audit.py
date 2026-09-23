"""Stop-time completion scope audit, and `/crew:done`'s scope check.

crew 1.0, lane T3 (docs/review/04-redesign.md, Hooks table: "diffs the whole
tree against the scope base, catching shell-made writes too, and refuses
`done` on out-of-scope paths").

The edit guard (`scope_guard.py`) sees only Write/Edit/MultiEdit/NotebookEdit.
A `sed -i`, a redirect, a formatter or a `git mv` never reaches it. This audit
reads the result instead of the tool call: every path that differs from the
ticket's scope base (`scope_base.resolve` -- the commit the ticket started
from, falling back to MORE, never less) across committed, staged, unstaged
and untracked changes. PATHS ONLY: `git diff --name-status -z -M <base>`
(the base tree against the working tree, which folds in committed, staged and
unstaged) plus `git ls-files --others --exclude-standard -z`. No file content
is read, so a Stop costs a path listing, not the review bundle. Renames
arrive with both ends and BOTH must be in scope: a rename moves a file out of
one path as much as into another. Git runs with `GIT_OPTIONAL_LOCKS=0`, so
the user's index is never rewritten.

What it cannot see, stated rather than implied: files git ignores (`.crew/*`
among them) and `.work/`, which is excluded on purpose (as the review bundle
excludes it).

Paths are printed with control characters escaped (`\n` in a filename would
otherwise add lines), and the whole message is capped at six PHYSICAL lines.

A path passes when it is inside the active ticket's `spec.md ## Touch`, read
from the same bytes the approval hash was checked against. When the ticket's
approval is not current or did not come from the user's prompt
(`crew_ticket.accepted`: stale, none, or a `cli` receipt without
`scope.allowCliApproval`), Touch itself is unapproved, so every changed path
fails: an edited spec cannot widen what the audit accepts until the user
approves it again. A broken active-ticket pointer fails the audit too.

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
import subprocess
import sys

import crew_ticket
import scope_base

MAX_LINES = 6
GIT_TIMEOUT = 60
# The review bundle's exclusion (`review_patch._EXCLUDE_SPEC`): crew's scratch
# space is never a changed path.
_ONLY = ["--", ".", ":(exclude).work"]


def _git_fields(top, args):
    """`git -C top <args>` NUL-split. Raises RuntimeError with git's stderr."""
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    try:
        done = subprocess.run(["git", "-C", top] + args, capture_output=True, env=env,
                              timeout=GIT_TIMEOUT, check=False, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"git {args[0]} could not run: {exc}") from exc
    if done.returncode != 0:
        err = done.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git {args[0]} failed ({done.returncode}): {err}")
    return done.stdout.decode("utf-8", errors="surrogateescape").split("\0")


def changed_paths(top, base):
    """Every path the tree changed since `base`, both ends of a rename or
    copy. Names only -- no blob or patch content is read."""
    sha = _git_fields(top, ["rev-parse", "--verify", base + "^{commit}"])[0].strip()
    fields = _git_fields(top, ["diff", "--name-status", "-z", "-M", "--no-ext-diff",
                               sha] + _ONLY)
    paths, i = set(), 0
    while i < len(fields):
        head = fields[i]
        if not head:
            i += 1
            continue
        width = 2 if head[:1] in ("R", "C") else 1
        paths.update(p for p in fields[i + 1:i + 1 + width] if p)
        i += 1 + width
    paths.update(p for p in _git_fields(top, ["ls-files", "--others", "--exclude-standard",
                                              "-z"] + _ONLY) if p)
    return sorted(paths)


def shown(path):
    """`path` with every non-printable character escaped, so a filename can
    never add a line to a hook message."""
    return "".join(c if c.isprintable() else
                   (f"\\x{ord(c):02x}" if ord(c) < 0x100 else f"\\u{ord(c):04x}")
                   for c in path)


def physical(lines):
    """`lines` as at most MAX_LINES physical lines, whatever they contain."""
    return "\n".join(lines).splitlines()[:MAX_LINES]


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
        return False, [f"completion audit: could not diff the tree: {shown(str(exc))}"]
    if not paths:
        return True, []
    # ONE read of spec.md: the hash check and the Touch below share the bytes.
    approval = crew_ticket.accepted(top, ticket)
    note = "" if source == scope_base.RECORDED else " (base is a fallback: shows MORE)"
    if approval["status"] != "approved":
        return False, [f"COMPLETION AUDIT: {ticket}'s Touch is not approved "
                       f"({approval['why']}), so no change can be judged in scope.",
                       f"  Changed since {base[:12]}{note}: "
                       + " ".join(shown(p) for p in paths[:8])
                       + (" ..." if len(paths) > 8 else ""),
                       f"  Ask the user to type `/crew:approve {ticket}`."]
    outside = [p for p in paths if not crew_ticket.in_touch(p, approval["touch"])]
    if not outside:
        return True, []
    listed = " ".join(shown(p) for p in outside[:8]) + (
        f" (+{len(outside) - 8} more)" if len(outside) > 8 else "")
    return False, [f"COMPLETION AUDIT: {len(outside)} changed path(s) outside {ticket}'s "
                   f"spec ## Touch{note}:",
                   f"  {listed}",
                   "  Revert them, or amend spec.md ## Touch and have the user type",
                   f"  `/crew:approve {ticket}`. Shell-made writes count."]


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
    ticket, source, broken = crew_ticket.resolve_active(root)
    if broken:
        mode, why = crew_ticket.effective_mode(root, None)
        ok, lines = False, [f"COMPLETION AUDIT: the active-ticket pointer is broken "
                            f"({shown(source)}); nothing can be audited against a ticket.",
                            "  Fix it with `crew_ticket.py activate --ticket <id>` or "
                            "`crew_ticket.py deactivate`."]
    elif not ticket:
        return 0
    else:
        mode, why = crew_ticket.effective_mode(root, ticket)
        try:
            ok, lines = audit(root, ticket)
        except Exception as exc:  # pylint: disable=broad-except
            ok, lines = False, [f"completion audit: failed ({type(exc).__name__}: "
                                f"{shown(str(exc))}); nothing was audited"]
    if ok:
        return 0
    if mode == "block":
        sys.stderr.write("".join(line + "\n" for line in physical(lines)))
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
    print("\n".join(physical(lines)))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
