"""Report which changed paths fall outside the open ticket's declared scope.

REPORT-ONLY, ALWAYS EXIT 0. This is called from verify-gate.sh and
verify-gate.ps1, both of which can exit 2 to block a turn. Nothing here may
change that: the scope layer was chosen as report-only precisely so it would
not take on the blocking-hook regression obligation, and an exit code leaking
out of this file would take it on by accident.

## Why a shared script rather than two implementations

`read_work` (crew_state.py) parses `.work/INDEX.md` with real rules -- a done
marker skips a line, a table status wins over a text marker, no in-progress
line yields None rather than a guess. Re-deriving that in bash AND in
PowerShell is two copies that drift from the original and from each other.
pm-pulse.sh made the same call for the same reason and says so in its header.

## Unknowns stay unknown

Every branch that cannot answer prints WHY rather than an empty list. An empty
`outside-scope:` line means "checked, nothing outside"; it must never also mean
"could not check". That collapse -- an unknown wearing the label of a check
that happened -- is this repository's named recurring defect, and a scope
report is exactly the shape that invites it: the reassuring output and the
uninformative output look identical.
"""
import fnmatch
import os
import re
import sys

import crew_state
import scope_base

# `- touch: path, path` under `## Scope`, per commands/ticket.md's template.
_TOUCH = re.compile(r"^\s*[-*]\s*touch\s*:\s*(.+?)\s*$", re.IGNORECASE)
_SPLIT = re.compile(r"[,\s]+")

# Where a ticket file can live, in the order work.md reads them. `tickets` is
# files mode; `cache` is what /crew:jira-sync, /crew:sdp-sync and
# /crew:obsidian-sync write.
_TICKET_DIRS = ("tickets", "cache")

# Sentinel: the ticket file INDEX.md names does not exist. Not the same answer
# as "the ticket declared no paths", and folding the two loses which to fix.
MISSING = object()


def declared_paths(root, ticket):
    """The globs a ticket says it may touch, or None when it does not say.

    None and [] are different answers and the caller must keep them apart:
    None is "the ticket declared nothing", [] is "it declared an empty list",
    and only the second would justify reporting every changed file.
    """
    # TWO locations, because the tracker decides which one exists. Files mode
    # keeps the ticket at .work/tickets/<id>.md; Jira, ServiceDesk Plus and
    # Obsidian Kanban modes keep it at .work/cache/<id>.md (commands/work.md
    # step 1). Reading only the first reported "the ticket file is missing"
    # for tickets that exist -- including on this repository, whose tracker is
    # obsidian, so the defect was live here on every turn.
    text = None
    for folder in _TICKET_DIRS:
        text = crew_state.read_text(
            os.path.join(root, ".work", folder, f"{ticket}.md"))
        if text is not None:
            break
    if text is None:
        # Distinct from "the ticket declared nothing": the file INDEX.md names
        # is not there. Different cause, different fix, so it gets its own
        # sentence rather than being folded into the commoner case.
        return MISSING
    for line in text.splitlines():
        found = _TOUCH.match(line)
        if not found:
            continue
        raw = found.group(1).replace("`", "").strip()
        # The template ships a literal placeholder. A ticket that still carries
        # it declared nothing, and treating `<paths>` as a glob would put every
        # changed file outside scope and teach the reader to ignore the line.
        if not raw or raw.startswith("<"):
            return None
        globs = [p for p in _SPLIT.split(raw) if p and not p.startswith("<")]
        return globs or None
    return None


# Crew's own bookkeeping. Updating the ticket, the handoff or the codemap IS
# the process working, not scope creep, and reporting it on every turn is how a
# report becomes noise people stop reading. Excluded before the comparison so
# the line stays about the CHANGE.
# Split by KIND, because the two need different tests. The directories are a
# prefix match; the file is an EXACT match. They were one tuple behind a single
# str.startswith, which silently excluded anything merely beginning with the
# name: measured, both `TODO.mdx` and `TODO.md.py` were dropped from the report
# as bookkeeping. A real source file vanishing from a scope report is the one
# failure this file must not have -- the reassuring output and the
# uninformative output looking identical again.
_BOOKKEEPING_DIRS = (".work/", ".crew/")
_BOOKKEEPING_FILES = ("TODO.md",)


def bookkeeping(path):
    return path.startswith(_BOOKKEEPING_DIRS) or path in _BOOKKEEPING_FILES


def gate_matches(path, pat):
    """The matcher verify-gate.sh embeds, character for character.

    KEPT IN LOCKSTEP with verify-gate.sh (the `def matches` inside its python
    heredoc) and its PowerShell twin in verify-gate.ps1. The report and the
    gate answer the same question -- does this path fall under this pattern --
    and a report that answers it differently from the gate that blocks the
    turn is worse than no report.

    fnmatch's `*` spans `/`, so `**/*.py` demands a literal slash and matches
    no root-level file at all: measured, fnmatch("main.py", "**/*.py") is
    False while fnmatch("src/main.py", "**/*.py") is True. A ticket declaring
    `**/*.py` therefore had its own root-level files reported OUTSIDE scope,
    which is how a scope line that names in-scope files teaches the reader to
    ignore the whole report. The gate already stripped the `**/` form; this
    file did not, and that was the entire defect.
    """
    cands = {pat}
    if pat.startswith("**/"):
        cands.add(pat[3:])
    cands.add(pat.replace("/**/", "/"))
    return any(fnmatch.fnmatch(path, c) for c in cands)


def matches(path, glob):
    """The gate's matcher, plus the bare-directory form a TICKET declares.

    A `- touch:` line is written by a person and routinely names a directory
    (`plugin/crew/hooks/`) where a verify.json rule would write a glob. Those
    two extra forms are a deliberate SUPERSET of the gate: every path the gate
    calls a match, this calls a match too, never the reverse. The direction
    matters -- a superset can only ever report FEWER files as outside scope,
    so the divergence cannot invent a scope violation the gate would not also
    see. Widening it further needs that argument to still hold.
    """
    if gate_matches(path, glob):
        return True
    stem = glob.rstrip("/")
    return fnmatch.fnmatch(path, stem + "/*") or path.startswith(stem + "/")


def outside(changed, globs):
    out = []
    for path in changed:
        if bookkeeping(path):
            continue
        if any(matches(path, g) for g in globs):
            continue
        out.append(path)
    return out


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    changed = [l.strip() for l in sys.stdin.read().splitlines() if l.strip()]

    try:
        ticket = crew_state.read_work(root).get("ticket")
    except Exception as exc:  # pylint: disable=broad-except
        sys.stderr.write(
            f"outside-scope: (could not read the ticket: {exc})\n")
        return 0

    if not ticket:
        sys.stderr.write("outside-scope: (no open ticket)\n")
        return 0

    globs = declared_paths(root, ticket)
    if globs is MISSING:
        sys.stderr.write(
            f"outside-scope: ({ticket} is open but its ticket file is "
            f"missing from both .work/tickets/{ticket}.md and "
            f".work/cache/{ticket}.md)\n")
        return 0
    if globs is None:
        sys.stderr.write(
            f"outside-scope: (cannot check - no declared paths in {ticket})\n")
        return 0

    # The list on stdin is what the GATE saw this turn, diffed from the commit
    # it last verified. That base advances on every clean pass, so a commit
    # verified on one turn has left the gate's list by the next while still
    # on the branch -- and since crew 0.19.95 a developer may commit on the
    # ticket's own branch. The ticket's own base (scope_base.py) does not
    # move. Union the two rather than replace: this report may name MORE
    # than the gate saw, never less, and when the base cannot be resolved the
    # gate's list still stands and the line below says the union did not.
    base_note = None
    try:
        base, source, reason = scope_base.resolve(root, ticket)
        ticket_wide = scope_base.changed(root, base) if base else None
    except Exception as exc:  # pylint: disable=broad-except
        base, source, ticket_wide = None, None, None
        reason = f"could not resolve: {exc}"
    # The marker goes ON the outside-scope line, not only on the scope-base
    # line under it. A reader (or a grep) takes the first line; a bare
    # `outside-scope:` produced from a fallback, or from this turn's list
    # alone because git could not answer, reads as "checked, nothing
    # outside" -- an unknown wearing the label of a check that happened. The
    # unknown has to survive into every line derived from it.
    if ticket_wide is None:
        suffix = f" (this turn only: {reason})"
        base_note = (f"scope-base: ({reason}; ticket-wide diff unavailable, "
                     "this turn's list only)")
    else:
        # A recorded-fallback reason already opens with "(fallback)"; one
        # marker per line, not two.
        note = reason.removeprefix("(fallback) ")
        suffix = "" if source == scope_base.RECORDED else f" (fallback: {note})"
        base_note = f"scope-base: {base[:12]} ({reason})"
        changed = sorted(set(changed) | set(ticket_wide))

    extra = outside(changed, globs)
    if extra:
        sys.stderr.write(f"outside-scope: {chr(32).join(sorted(extra))}{suffix}\n")
        sys.stderr.write(
            f"  {ticket} declares: {chr(32).join(globs)}\n"
            "  Report-only. Under the scope clause these belong in TODO.md "
            "with a reason, not fixed here.\n")
    else:
        sys.stderr.write(f"outside-scope:{suffix}\n")
    # After the list, not before: the first line of this report is the list,
    # and its readers -- human and test alike -- take it from there.
    sys.stderr.write(base_note + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
