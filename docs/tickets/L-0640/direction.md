# L-0640 direction - next.md: who a ticket waits on, and what happens next

Split from T-0037 on 2026-10-04 (size check: a second parser must not ride with L-0639's fail-closed derivation). Not yet approved by the owner.

## Ask
From the approved T-0037 direction (2026-09-26): fields `waiting-on: owner | agent | T-#### | external` and a one-line `next:`, plus the reason and revisit date of a `hold` and the successor of a `superseded` ticket.

## Facts
- The approved T-0037 spec decided these live in `.work/tickets/<id>/next.md`, one `key: value` per line, because any byte of spec.md other than the header status value stales the approval (`plugin/crew/hooks/scripts/crew_ticket.py:64-75` at origin/main 155fe6d8) and these fields change at every step.
- No `next.md` reader exists on origin/main (`git grep "next\.md" origin/main -- plugin/crew/hooks/scripts` is empty).
- `.work/` is gitignored apart from a named list, so next.md is local state like spec.md.

## Recommendation
Add `read_next(folder)` to `crew_ticket_state.py` and join its fields into `view`. Strict keys, strict values, every malformed value reported as a problem and never dropped.

## Depends on
L-0639 (`crew_ticket_state.py`, `view`).

## Open questions for the owner
- Who writes next.md? Default taken: nobody automatically in this slice. The owner or a lifecycle step writes it by hand; L-0550 and L-0551 only read it. A writer command is a later ticket if wanted.
- `revisit:` format. Default taken: ISO `YYYY-MM-DD` only.
