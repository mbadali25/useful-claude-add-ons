"""Report which changed paths fall outside the active ticket's approved Touch.

REPORT-ONLY, ALWAYS EXIT 0. This is called from verify-gate.sh and
verify-gate.ps1, both of which can exit 2 to block a turn. Nothing here may
change that: the scope layer was chosen as report-only precisely so it would
not take on the blocking-hook regression obligation, and an exit code leaking
out of this file would take it on by accident. The REFUSAL is `/crew:done`
check 3 (`completion_audit.py --check`), and, under `scope.mode: block`, the
completion audit's own Stop hook.

## The crew 1.0 contract, read the way the audit reads it (L-0711)

The active ticket is `crew_ticket.resolve_active`; its Touch is
`crew_ticket.accepted` (spec.md `## Touch`, from the same bytes the approval
hash was checked against); a path is in scope by `crew_ticket.in_touch`; and a
refresh artifact is admitted by the audit's own rule
(`completion_audit._outside_refresh_artifacts`). Those are the calls the scope
guard and the completion audit make, so this line and `/crew:done` cannot
disagree about a path. Until L-0711 this file read the pre-1.0 `- touch:` line
in `.work/tickets/<id>.md` or `.work/cache/<id>.md`, so every 1.0 ticket read
as "ticket file is missing" and a `sed -i` outside Touch was never named here.
A 0.20-layout ticket is now could-not-tell, never judged and never in scope.

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
import sys

import completion_audit
import crew_state
import crew_ticket
import scope_base

# Where a pre-1.0 ticket lived: files mode, then the tracker cache. Read only
# to say WHY such a ticket cannot be judged, never for its `- touch:` line.
_LEGACY_DIRS = ("tickets", "cache")


def legacy_ticket(top):
    """`(ticket, rel)` when `.work/INDEX.md`'s open ticket exists only in the
    pre-1.0 layout, else None."""
    try:
        ticket = crew_state.read_work(top).get("ticket")
        if not ticket or os.path.isdir(crew_ticket.ticket_dir(top, ticket)):
            return None
    except Exception:  # noqa: BLE001  # pylint: disable=broad-except  # any INDEX failure: not a legacy ticket
        return None
    for folder in _LEGACY_DIRS:
        rel = f".work/{folder}/{ticket}.md"
        if os.path.isfile(os.path.join(top, rel)):
            return ticket, rel
    return None


def approved_touch(top, ticket):
    """`(touch, approval, None)`, or `(None, None, why)` when the ticket's
    Touch cannot be judged. One `accepted` call: the Touch and the approval
    it travels with come from one read of spec.md, as in the audit."""
    spec = os.path.join(crew_ticket.ticket_dir(top, ticket), "spec.md")
    rel = os.path.relpath(spec, top).replace(os.sep, "/")
    text = crew_state.read_text(spec)
    if text is None:
        return None, None, f"{ticket} has no readable {rel}"
    entries, problems = crew_ticket.parse_touch(text)
    if not entries:
        return None, None, f"{rel}: {'; '.join(problems)}"
    approval = crew_ticket.accepted(top, ticket)
    if approval["status"] != "approved" or not approval["touch"]:
        return None, None, f"{ticket}'s ## Touch is not approved ({approval['why']})"
    return approval["touch"], approval, None


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
    """The gate's matcher, plus the bare-directory form.

    No longer what this report judges Touch with -- since L-0711 that is
    `crew_ticket.in_touch`, the audit's matcher. Kept because
    `test_crew_ticket` holds `crew_ticket.path_matches` to it where no `*`
    crosses a `/`, and it must stay a SUPERSET of the gate: every path the
    gate calls a match, this calls a match too, never the reverse.
    """
    if gate_matches(path, glob):
        return True
    stem = glob.rstrip("/")
    return fnmatch.fnmatch(path, stem + "/*") or path.startswith(stem + "/")


def outside(top, changed, touch, approval):
    """The changed paths `/crew:done` check 3 would refuse: not bookkeeping,
    not a refresh artifact the audit admits, not inside Touch."""
    judged = [p for p in changed if not bookkeeping(p)]
    judged = completion_audit._outside_refresh_artifacts(  # pylint: disable=protected-access
        top, judged, approval)
    return [p for p in judged if not crew_ticket.in_touch(p, touch)]


def _could_not_tell(why):
    sys.stderr.write(f"outside-scope: (could not tell - {why})\n")
    return 0


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    changed = [l.strip() for l in sys.stdin.read().splitlines() if l.strip()]
    try:
        return report(root, changed)
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-except  # report-only: never exit non-zero
        return _could_not_tell(f"{type(exc).__name__}: {exc}")


def report(root, changed):
    top = crew_ticket.toplevel(root)
    if not top:
        return _could_not_tell(f"{root} is not a git repository")
    ticket, source, broken = crew_ticket.resolve_active(top)
    if broken:
        return _could_not_tell(source)
    if not ticket:
        legacy = legacy_ticket(top)
        if legacy:
            return _could_not_tell(
                f"{legacy[0]} is in the pre-1.0 layout ({legacy[1]}); crew 1.0 reads "
                f".work/tickets/{legacy[0]}/spec.md ## Touch - run /crew:migrate")
        sys.stderr.write("outside-scope: (no open ticket)\n")
        return 0

    globs, approval, why = approved_touch(top, ticket)
    if why:
        return _could_not_tell(why)

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
        base, source, reason = scope_base.resolve(top, ticket)
        ticket_wide = scope_base.changed(top, base) if base else None
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

    extra = outside(top, changed, globs, approval)
    if extra:
        sys.stderr.write(f"outside-scope: {chr(32).join(sorted(extra))}{suffix}\n")
        sys.stderr.write(
            f"  {ticket} declares: {chr(32).join(globs)}\n"
            "  Report-only here; /crew:done check 3 refuses them. Revert them, "
            "file them to TODO.md, or amend ## Touch and re-approve.\n")
    else:
        sys.stderr.write(f"outside-scope:{suffix}\n")
    # After the list, not before: the first line of this report is the list,
    # and its readers -- human and test alike -- take it from there.
    sys.stderr.write(base_note + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
