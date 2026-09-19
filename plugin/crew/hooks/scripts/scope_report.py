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

# `- touch: path, path` under `## Scope`, per commands/ticket.md's template.
_TOUCH = re.compile(r"^\s*[-*]\s*touch\s*:\s*(.+?)\s*$", re.IGNORECASE)
_SPLIT = re.compile(r"[,\s]+")

# Sentinel: the ticket file INDEX.md names does not exist. Not the same answer
# as "the ticket declared no paths", and folding the two loses which to fix.
MISSING = object()


def declared_paths(root, ticket):
    """The globs a ticket says it may touch, or None when it does not say.

    None and [] are different answers and the caller must keep them apart:
    None is "the ticket declared nothing", [] is "it declared an empty list",
    and only the second would justify reporting every changed file.
    """
    path = os.path.join(root, ".work", "tickets", "%s.md" % ticket)
    text = crew_state.read_text(path)
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
_BOOKKEEPING = (".work/", ".crew/", "TODO.md")


def outside(changed, globs):
    out = []
    for path in changed:
        if path.startswith(_BOOKKEEPING) or path in _BOOKKEEPING:
            continue
        if any(fnmatch.fnmatch(path, g) or fnmatch.fnmatch(path, g.rstrip("/") + "/*")
               or path.startswith(g.rstrip("/") + "/") for g in globs):
            continue
        out.append(path)
    return out


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    changed = [l.strip() for l in sys.stdin.read().splitlines() if l.strip()]

    try:
        ticket = crew_state.read_work(root).get("ticket")
    except Exception as exc:  # pylint: disable=broad-except
        sys.stderr.write("outside-scope: (could not read the ticket: %s)\n" % exc)
        return 0

    if not ticket:
        sys.stderr.write("outside-scope: (no open ticket)\n")
        return 0

    globs = declared_paths(root, ticket)
    if globs is MISSING:
        sys.stderr.write(
            "outside-scope: (%s is open but .work/tickets/%s.md is missing)\n"
            % (ticket, ticket))
        return 0
    if globs is None:
        sys.stderr.write("outside-scope: (cannot check - no declared paths in %s)\n" % ticket)
        return 0

    extra = outside(changed, globs)
    if extra:
        sys.stderr.write("outside-scope: %s\n" % " ".join(sorted(extra)))
        sys.stderr.write(
            "  %s declares: %s\n"
            "  Report-only. Under the scope clause these belong in TODO.md with "
            "a reason, not fixed here.\n" % (ticket, " ".join(globs)))
    else:
        sys.stderr.write("outside-scope:\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
