"""PreToolUse plan-approval + scope guard on Write/Edit/MultiEdit/NotebookEdit.

crew 1.0, lane T3 (docs/review/04-redesign.md, Hooks table). The decision
lives here; `scope-guard.sh` and `scope-guard.ps1` only find a python and pipe
the payload in, so the two shells cannot disagree.

## What it decides, in order

1. `scope.mode` resolves to `off` (the default, and what a repo that never set
   the key gets) -> exit 0 before anything else is read.
2. A target under `<git-common-dir>/crew/` -- approval receipts, the review
   ledger, the active-ticket pointer, the ramp count -- or the scope base
   `.crew/.scope-base` is REFUSED in every mode but `off`, whether or not a
   ticket is active. Those files are what the guard and the Stop audit trust;
   an Edit that could write them could approve its own plan.
3. No active ticket (`crew_ticket.active_ticket`) -> allowed: the guard
   enforces a ticket's contract and there is no contract to enforce.
4. Otherwise every target must be the ticket's own `.work/tickets/<id>/` files
   (always writable, so the spec and plan can be amended), or -- with an
   approved, non-stale plan -- inside `spec.Touch`. Nothing else is exempt:
   not `.crew/`, not `TODO.md`, not `.claude/`, not crew's policy files.
   Put them in Touch if the ticket is meant to change them.

`block` refuses (exit 2, <= 6 lines on stderr). `report` allows, logs the row
to `.crew/guard.log` (never creating `.crew/`), and prints a `systemMessage`
so the note is visible. `auto` is `report` for the first ten tickets, then
`block` (crew_ticket.effective_mode).

## Paths

Each target is judged twice, and both must pass. The REAL path follows every
symlink and junction the way the OS will when it opens the file
(`role_write_guard._resolve_real_target`, reused rather than re-derived; case
is folded on Windows by `os.path.normcase` / fnmatch). The NAMED path --
normalised lexically, `..` collapsed -- is checked too whenever it lies inside
the worktree, so a link whose name is outside Touch cannot be used to write
into Touch any more than a link inside Touch can write out of it. A real path
outside the worktree is not a repository path and is allowed, unless it is in
the common git directory, which is never in scope.

Shell-made writes are not this hook's to see; the Stop-time
`completion_audit.py` diffs the whole tree for those.

## Failure

A payload that does not parse or names no path, under `block`, is refused --
an unclassifiable write is not evidence the write is in scope. An exception
this file did not anticipate fails closed when the configured mode is `block`
or `auto`, and open (with a note) under `report`.
"""
import json
import os
import sys
import time

import crew_ticket
import role_write_guard

TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
GUARD_LOG = os.path.join(".crew", "guard.log")
SCOPE_BASE = ".crew/.scope-base"


def _read_payload():
    try:
        raw = sys.stdin.buffer.read()
    except (OSError, ValueError):
        return None
    if raw[:3] == b"\xef\xbb\xbf":
        raw = raw[3:]
    try:
        data = json.loads(raw.decode("utf-8")) if raw.strip() else {}
    except (UnicodeDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def targets(data):
    """Every path a Write/Edit/MultiEdit/NotebookEdit call names."""
    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict):
        return []
    found = [tool_input.get(key) for key in ("file_path", "notebook_path")]
    for edit in tool_input.get("edits") or []:
        if isinstance(edit, dict):
            found.append(edit.get("file_path"))
    return [p for p in dict.fromkeys(found) if isinstance(p, str) and p]


def _under(path, directory):
    path, directory = os.path.normcase(path), os.path.normcase(directory)
    return path == directory or path.startswith(directory.rstrip(os.sep) + os.sep)


def _rel(path, top):
    """`path` relative to `top` with `/` separators, or None when outside."""
    try:
        rel = os.path.relpath(path, top)
    except ValueError:
        return None
    rel = rel.replace(os.sep, "/")
    return None if rel == ".." or rel.startswith("../") else rel


def classify(top, common, ticket, touch, approval, target, base):
    """(ok, reason) for one target path."""
    absolute = target if os.path.isabs(target) else os.path.join(base, target)
    real = role_write_guard._resolve_real_target(absolute)  # pylint: disable=protected-access
    named = os.path.normpath(absolute)
    real_rel, named_rel = _rel(real, top), _rel(named, top)
    if common and (_under(real, common) or _under(named, common)):
        return False, f"{target} is inside the git directory; never in scope"
    own = f".work/tickets/{ticket}/"
    checks = [r for r in (real_rel, named_rel) if r is not None]
    if not checks:
        return True, "outside the worktree"
    if all(os.path.normcase(r).startswith(os.path.normcase(own)) for r in checks):
        return True, "the ticket's own files"
    if approval["status"] != "approved":
        return False, (f"{ticket}: {approval['why']}" if approval["status"] == "stale"
                       else f"{ticket} has no approved plan")
    outside = [r for r in checks if not crew_ticket.in_touch(r, touch)]
    if real_rel is None and named_rel is not None:
        outside.append(f"{named_rel} -> {real} (outside the worktree)")
    if outside:
        return False, f"{outside[0]} is outside {ticket}'s spec ## Touch"
    return True, "in Touch"


def protected(top, state, target, base):
    """True when `target` names crew's approval/ledger state."""
    absolute = target if os.path.isabs(target) else os.path.join(base, target)
    real = role_write_guard._resolve_real_target(absolute)  # pylint: disable=protected-access
    named = os.path.normpath(absolute)
    for path in (real, named):
        if state and _under(path, state):
            return True
        rel = _rel(path, top)
        if rel is not None and os.path.normcase(rel) == os.path.normcase(SCOPE_BASE):
            return True
    return False


def _log(top, mode, decision, ticket, path, reason):
    row = "\t".join(str(c).replace("\t", " ").replace("\n", " ") for c in (
        int(time.time()), "scope", mode, decision, ticket or "-", path or "-", reason))
    try:
        log = os.path.join(top, GUARD_LOG)
        if os.path.isdir(os.path.dirname(log)):
            with open(log, "a", encoding="utf-8") as handle:
                handle.write(row + "\n")
    except OSError:
        pass


def _deny(lines):
    sys.stderr.write("".join(line + "\n" for line in lines[:6]))
    return 2


def _note(text):
    sys.stdout.write(json.dumps({"systemMessage": text}) + "\n")
    return 0


def decide(data):
    """The exit code for one payload. Writes its own stderr/stdout."""
    if data is None:
        return None
    if data.get("tool_name") not in TOOLS:
        return 0
    root = data.get("cwd") if isinstance(data.get("cwd"), str) else None
    root = root or os.environ.get("CLAUDE_PROJECT_DIR") or "."
    top = crew_ticket.toplevel(root)
    if not top:
        return 0
    configured, why = crew_ticket.configured_mode(top)
    if configured == "off":
        return 0
    common = crew_ticket.common_dir(root)
    state = os.path.join(common, "crew") if common else None
    paths = targets(data)
    base = os.path.abspath(root)
    for path in paths:
        if protected(top, state, path, base):
            _log(top, configured, "block", None, path, "crew approval/ledger state")
            return _deny([f"SCOPE GUARD: {path} is crew's approval/ledger state and is never "
                          "written by Write/Edit.",
                          "  Approve with `crew_ticket.py approve --ticket <id>` (run by you, "
                          "not the session)."])
    ticket, _source = crew_ticket.active_ticket(root)
    if not ticket:
        return 0
    mode, why = crew_ticket.effective_mode(root, ticket)
    if not paths:
        reason = "the call names no file path, so its scope cannot be judged"
        verdicts = [("-", False, reason)]
    else:
        touch = crew_ticket.touch_for(top, ticket)
        approval = crew_ticket.status(root, ticket)
        verdicts = [(p,) + classify(top, common, ticket, touch, approval, p, base)
                    for p in paths]
    bad = [(p, reason) for p, ok, reason in verdicts if not ok]
    if not bad:
        return 0
    path, reason = bad[0]
    _log(top, mode, "block" if mode == "block" else "report", ticket, path, reason)
    if mode == "block":
        return _deny([f"SCOPE GUARD: refused {data.get('tool_name')} on {path}.",
                       f"  Reason: {reason}.",
                       f"  To widen scope: amend .work/tickets/{ticket}/spec.md ## Touch "
                       "(and plan.md), then ask the user to run",
                       f"  `crew_ticket.py approve --ticket {ticket}`. ({why})"])
    return _note(f"scope-guard (report, would block): {path} - {reason}. ({why})")


def main():
    data = _read_payload()
    try:
        code = decide(data)
    except Exception as exc:  # pylint: disable=broad-except
        root = (data or {}).get("cwd") if isinstance((data or {}).get("cwd"), str) else "."
        try:
            configured, _ = crew_ticket.configured_mode(crew_ticket.toplevel(root) or root)
        except Exception:  # pylint: disable=broad-except
            configured = "block"
        if configured in ("block", "auto"):
            return _deny([f"SCOPE GUARD: could not judge this write ({type(exc).__name__}: "
                          f"{exc}); failing closed under scope.mode {configured}."])
        sys.stderr.write(f"scope-guard: could not judge this write ({type(exc).__name__}); "
                         "allowed.\n")
        return 0
    if code is None:
        # Unparseable payload: fail closed only where the repo asked for block.
        try:
            top = crew_ticket.toplevel(os.environ.get("CLAUDE_PROJECT_DIR") or ".")
            configured, _ = crew_ticket.configured_mode(top) if top else ("off", "")
        except Exception:  # pylint: disable=broad-except
            configured = "block"
        if configured == "block":
            return _deny(["SCOPE GUARD: the hook payload did not parse; failing closed "
                          "under scope.mode block."])
        sys.stderr.write("scope-guard: hook payload did not parse; allowed unjudged.\n")
        return 0
    return code


if __name__ == "__main__":
    sys.exit(main())
