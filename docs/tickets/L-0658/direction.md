# A `--goal` handoff is checked against the goal file, not the branch and head (L-0658)

Split from T-0056 on 2026-10-04. Status: seed, written for hand-off; filed as L-0658.

## Ask
Owner, 2026-09-26, on T-0056: an autopilot goal must survive a clear and a handoff note, "so that if
something happens and we resume, it would resume that goal."

## Problem (origin/main `155fe6d8`)
A handoff is used only when its `branch:` and `head:` equal this checkout. That is right for a ticket: one
ticket, one branch. A goal walks across ticket branches. A goal handoff written on ticket 2's branch and
read after ticket 3's branch was checked out, or after one more commit, is thrown away. The check is in
three places: `plugin/crew/hooks/scripts/crew_autopilot.py:650-661` (`_handoff_ticket`), `:1507-1513`
(status's `_resume_line`), and `plugin/crew/hooks/scripts/crew_resume.py:694-701` (`decide`, the auto-resume path).

## Options
1. **For the goal form only, the goal file replaces the branch and head check (recommended).** The handoff
   is a pointer; the goal file says whether the goal is `running`, and each ticket's state on disk says
   where to continue. The ticket form keeps its check unchanged. Every other auto-resume condition stays:
   the author record, consumed-once, the progress fingerprint, the armed setting.
2. Record the branch in the goal file and compare against that. It fails the same way one commit later.
3. Drop the check for every handoff. Rejected: it is what stops a ticket handoff from another branch.

## Recommendation
Option 1. A goal handoff is usable when the goal file is readable and its run state is `running`. `stopped`
is named with its reason and not resumed; `done` and unreadable are refused with the reason. "Could not
read the goal file" is its own answer and is never treated as "no goal".

## Open questions for the owner (default taken)
- Should auto-resume (typing the command after `/clear`) be allowed for a goal handoff whose branch differs?
  Default: yes, under Option 1's conditions, because the author record and consumed-once rules still bind
  it to this session and this note. The stricter alternative is to name the command and never type it.

## Depends on
T-0056 (run state in the goal file), L-0541 (`--goal` resume in `resume_target`), T-0012, T-0006 (merged).
