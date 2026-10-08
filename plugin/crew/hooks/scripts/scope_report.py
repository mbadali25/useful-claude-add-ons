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
(`completion_audit._outside_refresh_artifacts`); bookkeeping is what the audit
leaves out, nothing wider; and a path byte-identical to merged main is not
counted, from the gate's list as from the ticket-wide one. Those are the calls
the scope guard and the completion audit make, so on the same tree this line
names the paths `/crew:done` check 3 refuses. Until L-0711 this file read the pre-1.0 `- touch:` line
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
import merged_main
import scope_base

# Where a pre-1.0 ticket lived: files mode, then the tracker cache. Read only
# to say WHY such a ticket cannot be judged, never for its `- touch:` line.
_LEGACY_DIRS = ("tickets", "cache")


def unresolved_index_ticket(top):
    """Why `.work/INDEX.md`'s open ticket cannot be judged, or None when INDEX
    names no open ticket. Called only when `crew_ticket.resolve_active` found
    none, so a ticket INDEX names here is one crew 1.0 could not resolve:
    pre-1.0, an id `crew_ticket` refuses, or no `.work/tickets/<id>/`
    directory. Each is could-not-tell (review round 3): "(no open ticket)"
    is a true statement only when INDEX names none, and an INDEX that cannot
    be read is not that statement either."""
    try:
        ticket = crew_state.read_work(top).get("ticket")
    except (OSError, ValueError) as exc:
        return f".work/INDEX.md could not be read ({type(exc).__name__}: {exc})"
    if not ticket:
        return None
    try:
        folder = crew_ticket.ticket_dir(top, ticket)
    except crew_ticket.TicketError as exc:
        return f".work/INDEX.md's open ticket {ticket!r} is not a ticket id crew accepts ({exc})"
    for legacy in _LEGACY_DIRS:
        rel = f".work/{legacy}/{ticket}.md"
        if os.path.isfile(os.path.join(top, rel)):
            return (f"{ticket} is in the pre-1.0 layout ({rel}); crew 1.0 reads "
                    f".work/tickets/{ticket}/spec.md ## Touch - run /crew:migrate")
    if not os.path.isdir(folder):
        return (f".work/INDEX.md names {ticket} as open, but .work/tickets/{ticket}/ "
                "does not exist")
    return f".work/INDEX.md names {ticket} as open, but crew_ticket did not resolve it"


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


def bookkeeping(path):
    """What `/crew:done` check 3 leaves out, and nothing wider: `.work/` (the
    audit's `:(exclude).work` pathspec) and `crew_ticket.CREW_BOOKKEEPING_PATHS`.

    Owner ruling, 2026-10-08 (L-0711 review round 3): acceptance check 5 --
    the report and the audit agree on the same tree -- wins over the spec's
    exclusion that froze this file's own wider list (all of `.crew/` and
    `TODO.md`). That list printed a clean `outside-scope:` for a `TODO.md` or
    `.crew/verify.json` write outside Touch that the audit refuses. Exact
    matches only, as before: `TODO.mdx` was never bookkeeping.
    """
    return path == ".work" or path.startswith(".work/") or crew_ticket.is_crew_bookkeeping(path)


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
        unresolved = unresolved_index_ticket(top)
        if unresolved:
            return _could_not_tell(unresolved)
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
    # Review round 3: the merged-main filter reaches the gate's list too. That
    # list is diffed from the last verified commit, so after a merge of main
    # it carries main's own changes; a path the audit drops as byte-identical
    # to merged main is dropped from it before the union.
    base_note = None
    try:
        base, source, reason = scope_base.resolve(top, ticket)
        ticket_wide, dropped = ticket_changes(top, base) if base else (None, set())
    except Exception as exc:  # pylint: disable=broad-except
        base, source, ticket_wide, dropped = None, None, None, set()
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
        changed = [p for p in changed if p not in dropped]
        changed = sorted(set(changed) | set(ticket_wide))

    extra = outside(top, changed, globs, approval)
    if extra:
        sys.stderr.write(f"outside-scope: {chr(32).join(sorted(extra))}{suffix}\n")
        sys.stderr.write(
            f"  {ticket} declares: {chr(32).join(globs)}\n"
            "  Report-only here; /crew:done check 3 refuses them. Revert them "
            "(a follow-up goes to TODO.md), or amend ## Touch and re-approve.\n")
    else:
        sys.stderr.write(f"outside-scope:{suffix}\n")
    # After the list, not before: the first line of this report is the list,
    # and its readers -- human and test alike -- take it from there.
    sys.stderr.write(base_note + "\n")
    return 0


def ticket_changes(top, base):
    """`(kept, dropped)`. `kept` is the completion audit's own changed list
    since `base` (review round 1): both ends of a rename, and paths
    byte-identical to merged main left out, exactly as `/crew:done` check 3
    counts them. `dropped` is the set that rule left out -- the audit's own
    second listing -- for the gate's list to lose too (review round 3).
    `(None, set())` when git could not answer, so the line says the list is
    this turn's only."""
    merged = merged_main.resolve(top, base)
    try:
        kept = completion_audit.changed_paths(top, base, merged)
        if not merged.get("applies"):
            return kept, set()
        return kept, set(completion_audit.changed_paths(top, base)) - set(kept)
    except RuntimeError:
        return None, set()


if __name__ == "__main__":
    sys.exit(main())
